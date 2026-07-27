# /opt/pontua/AutoPonto/backend_api/lifecycle_hooks.py
"""
Gatilhos dos e-mails do ciclo de vida — Sistema Ponto

Toda a lógica de "quando mandar o quê" mora aqui. Os arquivos de
produção só chamam uma função destas — assim um erro aqui nunca
derruba download, cadastro ou webhook.

TRAVA MESTRA: nada é enviado enquanto LIFECYCLE_EMAILS_ENABLED não
estiver 'true' no .env. O rastreio de atividade continua funcionando
mesmo desligado, para que os dados já estejam prontos quando ligar.
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime, timezone

import lifecycle_email_service as mailer

TRIAL_PAGES = 50
LIMIAR_TRIAL = 40          # 80% de 50
LIMIAR_PLANO = 0.80        # 80% das páginas incluídas
PLANOS_PAGOS = {'basic': 200, 'standard': 500, 'premium': 1500}


def emails_ligados() -> bool:
    return os.getenv('LIFECYCLE_EMAILS_ENABLED', 'false').lower() in ('1', 'true', 'yes', 'on')


def _agora():
    return datetime.now(timezone.utc)


def _ciclo(user) -> str:
    """Chave do ciclo atual — permite repetir e-mails 1x por mês."""
    d = getattr(user, 'next_reset_date', None) or getattr(user, 'last_renewal_at', None)
    if d:
        return d.strftime('%Y-%m')
    return _agora().strftime('%Y-%m')


# ── Envio: tenta a fila, cai para síncrono ────────────────────────────

def _job_enviar(user_id, tipo, contexto, ciclo):
    """Executado pelo worker RQ."""
    from auth_service import app, User
    with app.app_context():
        u = User.query.get(user_id)
        if u:
            mailer.send(u, tipo, contexto, ciclo)


def _disparar(user, tipo, contexto=None, ciclo=None):
    """Enfileira o envio. Nunca levanta exceção para o chamador."""
    if not emails_ligados():
        print(f"[CICLO] (desligado) enviaria '{tipo}' para {user.email}")
        return False
    try:
        from redis import Redis
        from rq import Queue
        url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        q = Queue('geral_queue', connection=Redis.from_url(url))
        q.enqueue(_job_enviar, user.id, tipo, contexto or {}, ciclo,
                  job_timeout=120)
        print(f"[CICLO] '{tipo}' enfileirado para {user.email}")
        return True
    except Exception as e:
        print(f"[CICLO] Fila indisponível ({e}); enviando direto.")
        try:
            return mailer.send(user, tipo, contexto or {}, ciclo)
        except Exception as e2:
            print(f"[CICLO] Falha no envio de '{tipo}': {e2}")
            return False


# ── Gancho: cadastro ──────────────────────────────────────────────────

def on_user_registered(user):
    """Chamado após criar a conta (e verificar o e-mail)."""
    try:
        if (user.role or 'user') == 'admin' or getattr(user, 'organization_id', None):
            return
        _disparar(user, 'welcome')
    except Exception:
        traceback.print_exc()


# ── Gancho: download concluído ────────────────────────────────────────

def on_download_completed(user):
    """
    Chamado depois que as páginas foram contabilizadas.

    Faz três coisas: marca atividade (sempre, mesmo desligado), avisa
    quando o teste está acabando e avisa quando acabou. A trava de
    duplicidade fica no email_event, então não precisa saber o valor
    anterior de page_count.
    """
    try:
        from auth_service import db
        user.last_activity_at = _agora()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        plano = (user.plan_status or 'free').lower()
        paginas = user.page_count or 0

        if getattr(user, 'organization_id', None) or (user.role or '') == 'admin':
            return

        # ── Free trial ────────────────────────────────────────────
        if plano == 'free':
            if paginas >= TRIAL_PAGES:
                _enviar_fim_do_trial(user)
            elif paginas >= LIMIAR_TRIAL:
                _disparar(user, 'trial_80')
            return

        # ── Assinante: aviso de uso alto, 1x por ciclo ─────────────
        incluidas = PLANOS_PAGOS.get(plano)
        if incluidas and paginas >= incluidas * LIMIAR_PLANO:
            _disparar(user, 'high_usage', ciclo=_ciclo(user))

    except Exception:
        traceback.print_exc()


def _enviar_fim_do_trial(user):
    """Trial esgotado: com cupom se passar no portão, senão sem."""
    if mailer.already_sent(user.id, 'trial_end_coupon') or \
       mailer.already_sent(user.id, 'trial_end_plain'):
        return

    contexto, tipo = {}, 'trial_end_plain'
    try:
        from discount_service import create_welcome_promotion_code
        from datetime import timedelta
        dados = create_welcome_promotion_code(user)
        if dados:
            validade = (datetime.fromisoformat(dados['expira_em'])
                        - timedelta(hours=3))     # UTC -> horário de Brasília
            frontend = os.getenv('FRONTEND_URL', 'https://sistemaponto.com')
            contexto = {
                'codigo': dados['codigo'],
                'validade': validade.strftime('%d/%m/%Y'),
                'pct_mes_1': dados['pct_mes_1'],
                'pct_mes_2_3': dados['pct_mes_2_3'],
                'link': f"{frontend}/planos?cupom={dados['codigo']}",
                'expira_em_ts': dados['expira_em_ts'],
            }
            tipo = 'trial_end_coupon'
    except Exception as e:
        print(f"[CICLO] Falha ao gerar cupom de {user.email}: {e}. "
              f"Enviando versão sem cupom.")

    _disparar(user, tipo, contexto)


# ── Ganchos: Stripe ───────────────────────────────────────────────────

def on_subscription_started(user):
    """Primeira assinatura confirmada."""
    try:
        from auth_service import db
        user.last_renewal_at = _agora()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        _disparar(user, 'subscribed')
    except Exception:
        traceback.print_exc()


def on_renewal(user, usadas_ciclo_anterior=0):
    """Renovação mensal paga. Chamar ANTES de zerar o page_count."""
    try:
        from auth_service import db
        ciclo_anterior = _ciclo(user)
        user.last_renewal_at = _agora()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        _disparar(user, 'renewal',
                  {'usadas_anterior': usadas_ciclo_anterior},
                  ciclo=ciclo_anterior)
    except Exception:
        traceback.print_exc()


def on_payment_failed(user, valor=None):
    try:
        ctx = {'valor': valor} if valor else {}
        _disparar(user, 'payment_failed', ctx, ciclo=_ciclo(user))
    except Exception:
        traceback.print_exc()


def on_subscription_ended(user):
    try:
        _disparar(user, 'subscription_ended')
    except Exception:
        traceback.print_exc()


# ── Diagnóstico ───────────────────────────────────────────────────────

if __name__ == "__main__":
    from auth_service import app, User

    print("=" * 66)
    print(" GANCHOS DO CICLO DE VIDA")
    print("=" * 66)
    print(f" Envio automático: {'LIGADO' if emails_ligados() else 'DESLIGADO'}")
    if not emails_ligados():
        print(" Para ligar, adicione no .env:")
        print("   LIFECYCLE_EMAILS_ENABLED=true")
    print("-" * 66)

    with app.app_context():
        usuarios = User.query.filter(User.role != 'admin').order_by(User.id).all()
        print(" O que dispararia no próximo download de cada um:\n")
        for u in usuarios:
            plano = (u.plan_status or 'free').lower()
            pg = u.page_count or 0
            if u.organization_id:
                acao = 'nada (conta de empresa)'
            elif plano == 'free':
                if pg >= TRIAL_PAGES:
                    acao = 'trial_end_coupon (ou _plain)'
                elif pg >= LIMIAR_TRIAL:
                    acao = 'trial_80'
                else:
                    acao = 'nada (só marca atividade)'
            elif plano in PLANOS_PAGOS:
                inc = PLANOS_PAGOS[plano]
                acao = ('high_usage' if pg >= inc * LIMIAR_PLANO
                        else f'nada ({pg}/{inc})')
            else:
                acao = f'nada (plano {plano})'
            print(f"  {u.email[:36]:38} {plano:10} {pg:>4}pg  ->  {acao}")
    print("=" * 66)
