# /opt/pontua/AutoPonto/backend_api/email_admin_api.py
"""
Painel de e-mails + descadastro — Sistema Ponto

Três endpoints:
  GET /api/admin/email-events            lista de usuários + último e-mail
  GET /api/admin/email-events/<user_id>  histórico completo de um usuário
  GET /api/email/unsubscribe             descadastro público (LGPD)

Autocontido: faz a própria checagem de admin, sem depender de decorator
externo. Registrar com register_email_admin_routes(app).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import jsonify, request, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity

import lifecycle_email_service as mailer

TRIAL = 50

ROTULOS = {
    'welcome': 'Boas-vindas',
    'nudge_d1': 'Posso ajudar?',
    'reminder': 'Lembrete',
    'last_call': 'Última chamada',
    'trial_80': 'Quase no fim',
    'trial_end_coupon': 'Trial acabou + cupom',
    'trial_end_plain': 'Trial acabou',
    'coupon_expiring': 'Cupom expirando',
    'subscribed': 'Obrigado por assinar',
    'renewal': 'Renovação',
    'idle_subscriber': 'Plano parado',
    'high_usage': 'Uso alto',
    'payment_failed': 'Pagamento falhou',
    'subscription_ended': 'Assinatura encerrada',
    'winback': 'Win-back',
    'winback_ex': 'Win-back ex-assinante',
    'reactivate_partial': 'Saldo parado',
    'reactivate_never': 'Nunca testou',
}


def _usuario_atual(User):
    """Resolve o usuário do JWT (identidade pode ser e-mail ou id)."""
    ident = get_jwt_identity()
    if ident is None:
        return None
    u = User.query.filter_by(email=str(ident)).first()
    if u:
        return u
    try:
        return User.query.get(int(ident))
    except (TypeError, ValueError):
        return None


def _segmento(u):
    plano = (u.plan_status or 'free').lower()
    if (u.role or '') == 'admin':
        return 'admin'
    if u.organization_id:
        return 'empresa'
    if plano in ('basic', 'standard', 'premium'):
        return 'assinante'
    if plano == 'inactive':
        return 'ex-assinante'
    if plano == 'past_due':
        return 'pgto pendente'
    pg = u.page_count or 0
    if pg >= TRIAL:
        return 'S1 esgotou'
    if pg >= 40:
        return 'S2 quase no fim'
    if pg >= 1:
        return 'S3 usou parte'
    return 'S4 nunca usou'


def _iso(dt):
    return dt.isoformat() if dt else None


def register_email_admin_routes(app):
    from auth_service import db, User, EmailEvent

    # ── 1. Lista geral ────────────────────────────────────────────────
    @app.route('/api/admin/email-events', methods=['GET'])
    @jwt_required()
    def admin_email_events():
        atual = _usuario_atual(User)
        if not atual or (atual.role or '') != 'admin':
            return jsonify({'msg': 'Acesso restrito.'}), 403

        # Último evento de cada usuário (base pequena: resolve em memória)
        ultimos, contagem = {}, {}
        for ev in EmailEvent.query.order_by(EmailEvent.sent_at.desc()).all():
            contagem[ev.user_id] = contagem.get(ev.user_id, 0) + 1
            if ev.user_id not in ultimos:
                ultimos[ev.user_id] = ev

        filtro = (request.args.get('segmento') or '').strip().lower()
        linhas = []
        for u in User.query.order_by(User.id).all():
            seg = _segmento(u)
            if filtro and filtro not in seg.lower():
                continue
            ev = ultimos.get(u.id)
            linhas.append({
                'user_id': u.id,
                'email': u.email,
                'nome': (u.first_name or '').strip() or None,
                'plan_status': u.plan_status,
                'page_count': u.page_count or 0,
                'segmento': seg,
                'email_opt_out': bool(getattr(u, 'email_opt_out', False)),
                'created_at': _iso(u.created_at),
                'last_activity_at': _iso(u.last_activity_at),
                'total_emails': contagem.get(u.id, 0),
                'ultimo_email': ({
                    'tipo': ev.email_type,
                    'rotulo': ROTULOS.get(ev.email_type, ev.email_type),
                    'status': ev.status,
                    'sent_at': _iso(ev.sent_at),
                } if ev else None),
            })

        por_tipo = {}
        for ev in EmailEvent.query.all():
            por_tipo[ev.email_type] = por_tipo.get(ev.email_type, 0) + 1

        return jsonify({
            'usuarios': linhas,
            'total_usuarios': len(linhas),
            'total_emails': EmailEvent.query.count(),
            'falhas': EmailEvent.query.filter_by(status='failed').count(),
            'por_tipo': [{'tipo': t, 'rotulo': ROTULOS.get(t, t), 'total': n}
                         for t, n in sorted(por_tipo.items(),
                                            key=lambda x: -x[1])],
        }), 200

    # ── 2. Histórico de um usuário ────────────────────────────────────
    @app.route('/api/admin/email-events/<int:user_id>', methods=['GET'])
    @jwt_required()
    def admin_email_events_user(user_id):
        atual = _usuario_atual(User)
        if not atual or (atual.role or '') != 'admin':
            return jsonify({'msg': 'Acesso restrito.'}), 403

        u = User.query.get(user_id)
        if not u:
            return jsonify({'msg': 'Usuário não encontrado.'}), 404

        eventos = (EmailEvent.query.filter_by(user_id=user_id)
                   .order_by(EmailEvent.sent_at.desc()).all())
        historico = []
        for ev in eventos:
            try:
                meta = json.loads(ev.meta or '{}')
            except Exception:
                meta = {}
            historico.append({
                'id': ev.id,
                'tipo': ev.email_type,
                'rotulo': ROTULOS.get(ev.email_type, ev.email_type),
                'status': ev.status,
                'sent_at': _iso(ev.sent_at),
                'assunto': meta.get('assunto'),
                'cupom': meta.get('codigo'),
                'validade': meta.get('validade'),
                'erro': meta.get('erro'),
            })

        return jsonify({
            'usuario': {
                'id': u.id,
                'email': u.email,
                'nome': (u.first_name or '').strip() or None,
                'plan_status': u.plan_status,
                'page_count': u.page_count or 0,
                'segmento': _segmento(u),
                'email_opt_out': bool(getattr(u, 'email_opt_out', False)),
                'created_at': _iso(u.created_at),
                'last_activity_at': _iso(u.last_activity_at),
                'last_renewal_at': _iso(u.last_renewal_at),
            },
            'historico': historico,
            'total': len(historico),
        }), 200

    # ── 3. Descadastro público (LGPD) ─────────────────────────────────
    @app.route('/api/email/unsubscribe', methods=['GET'])
    def email_unsubscribe():
        try:
            user_id = int(request.args.get('u', ''))
        except (TypeError, ValueError):
            return _pagina('Link inválido',
                           'Este link de descadastro não é válido.'), 400

        token = request.args.get('t', '')
        if not mailer.verify_unsubscribe_token(user_id, token):
            return _pagina('Link inválido',
                           'Este link de descadastro não é válido ou expirou.'), 400

        u = User.query.get(user_id)
        if not u:
            return _pagina('Conta não encontrada',
                           'Não localizamos esta conta.'), 404

        if not u.email_opt_out:
            u.email_opt_out = True
            try:
                db.session.commit()
                print(f"[EMAIL] Descadastro: {u.email}")
            except Exception as e:
                db.session.rollback()
                print(f"[EMAIL] Erro no descadastro de {u.email}: {e}")
                return _pagina('Erro',
                               'Não foi possível concluir. Tente novamente.'), 500

        return _pagina(
            'Pronto, você foi descadastrado',
            f'<strong>{u.email}</strong> não receberá mais e-mails de novidades '
            f'e lembretes.<br><br>Sua conta continua ativa e você seguirá '
            f'recebendo apenas mensagens essenciais, como confirmação de '
            f'pagamento e recuperação de senha.'), 200

    print("[EMAIL-ADMIN] Modulo de painel de e-mails carregado. "
          "3 endpoints registrados.")


def _pagina(titulo, mensagem):
    """Página HTML simples, no mesmo tema dos e-mails."""
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo} — Sistema Ponto</title></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;padding:60px 20px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#161b22;border-radius:12px;border:1px solid #30363d;max-width:520px;width:100%;">
        <tr><td style="background:linear-gradient(135deg,#1a3a5c,#0d2137);padding:30px 40px;text-align:center;">
          <h1 style="margin:0;color:#4a9eff;font-size:22px;font-weight:700;">Sistema Ponto</h1>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:#e6edf3;font-size:20px;">{titulo}</h2>
          <p style="margin:0;color:#8b949e;font-size:15px;line-height:1.6;">{mensagem}</p>
        </td></tr>
        <tr><td style="padding:24px 40px;border-top:1px solid #21262d;text-align:center;">
          <p style="margin:0;color:#6e7681;font-size:12px;">sistemaponto.com</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp
