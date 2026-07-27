# /opt/pontua/AutoPonto/backend_api/discount_service.py
"""
Composicao central de descontos — Sistema Ponto

Motivo de existir: dois sistemas (indicacoes e boas-vindas) escrevem
descontos na mesma assinatura. Se cada um escrever direto com
Subscription.modify(discounts=[...]), o segundo APAGA o primeiro, porque
essa lista substitui e nao soma. Todo desconto passa por aqui.

Regras (aprovadas):
  - Boas-vindas: 10%, 3 meses, uma vez na vida, so quem nunca pagou
  - Indicacao:   10%, 1 mes, para indicado e indicador
  - Acumulam:    mes 1 = 20%, meses 2 e 3 = 10%
  - Teto:        50% no total
"""
from __future__ import annotations

import os
import secrets
import string
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe

# ── Parametros ────────────────────────────────────────────────────────
WELCOME_PCT      = 10
WELCOME_MONTHS   = 3
REFERRAL_PCT     = 10
MAX_TOTAL_PCT    = 50
EXPIRY_DAYS      = 7

CODE_PREFIX      = "BV"
CODE_ALPHABET    = string.ascii_uppercase + string.digits
CODE_RANDOM_LEN  = 6

# IDs fixos criados por criar_cupons_stripe.py (.env pode sobrescrever)
COUPON_WELCOME_3M      = os.getenv('STRIPE_COUPON_WELCOME_3M',    'pontua_bv10_3m')
COUPON_WELCOME_REF_1ST = os.getenv('STRIPE_COUPON_WELCOME_REF',   'pontua_bv20_once')
COUPON_WELCOME_REST    = os.getenv('STRIPE_COUPON_WELCOME_REST',  'pontua_bv10_rest2m')
COUPON_REFERRAL_ONCE   = os.getenv('STRIPE_COUPON_REFERRAL_ONCE', 'pontua_ref10_once')

ACTIVE_PAID_PLANS = {"basic", "standard", "premium"}

# A versao padrao da conta (2025-09-30.clover) nao aceita mais 'coupon'
# em /v1/promotion_codes: retorna 400 "unknown parameter". Fixamos a
# versao SO nessas chamadas; o resto do sistema segue no padrao.
STRIPE_API_PROMO = os.getenv('STRIPE_API_VERSION_PROMO', '2024-06-20')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lazy():
    """Import tardio: evita import circular com auth_service."""
    from auth_service import db, User, EmailEvent, get_or_create_stripe_customer
    return db, User, EmailEvent, get_or_create_stripe_customer


def _gerar_codigo() -> str:
    sufixo = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_RANDOM_LEN))
    return f"{CODE_PREFIX}{WELCOME_PCT}{sufixo}"


# ══════════════════════════════════════════════════════════════════════
# ELEGIBILIDADE
# ══════════════════════════════════════════════════════════════════════

def is_eligible_for_welcome(user) -> tuple[bool, str]:
    """
    Portao do cupom de boas-vindas. Retorna (elegivel, motivo).

    Nao verifica indicacao nem creditos: descontos acumulam.
    """
    plano = (user.plan_status or 'free').lower()
    if plano != 'free':
        return False, f"plano '{plano}' (cupom e so para free trial)"
    if getattr(user, 'organization_id', None):
        return False, "conta de empresa (fluxo B2B proprio)"
    if (user.role or 'user') == 'admin':
        return False, "conta admin"
    if getattr(user, 'email_opt_out', False):
        return False, "usuario pediu para nao receber e-mails"

    # Nunca pagou nada — confirmado no proprio Stripe, nao so no banco
    if user.stripe_customer_id:
        try:
            subs = stripe.Subscription.list(
                customer=user.stripe_customer_id, status='all', limit=1
            )
            if subs.data:
                return False, "ja teve assinatura no Stripe"
        except Exception as e:
            return False, f"nao foi possivel verificar no Stripe ({e})"

    return True, "elegivel"


def has_pending_referral(user) -> bool:
    """True se o usuario foi indicado e a indicacao ainda nao converteu."""
    if not getattr(user, 'referred_by_code', None):
        return False
    try:
        from auth_service import Referral
        return Referral.query.filter_by(
            referred_id=user.id, status='pending'
        ).first() is not None
    except Exception:
        return bool(user.referred_by_code)


def descrever_beneficio(user) -> dict:
    """Quanto a pessoa recebe por mes. Usado no e-mail e no painel."""
    com_indicacao = has_pending_referral(user)
    if com_indicacao:
        return {
            'estrutura': 'welcome_ref',
            'pct_mes_1': WELCOME_PCT + REFERRAL_PCT,
            'pct_mes_2_3': WELCOME_PCT,
            'coupon_checkout': COUPON_WELCOME_REF_1ST,
            'precisa_complemento': True,
        }
    return {
        'estrutura': 'welcome',
        'pct_mes_1': WELCOME_PCT,
        'pct_mes_2_3': WELCOME_PCT,
        'coupon_checkout': COUPON_WELCOME_3M,
        'precisa_complemento': False,
    }


# ══════════════════════════════════════════════════════════════════════
# GERACAO DO CODIGO PESSOAL
# ══════════════════════════════════════════════════════════════════════

def create_welcome_promotion_code(user) -> Optional[dict]:
    """
    Cria um promotion code exclusivo do usuario.

    Travas do proprio Stripe:
      customer               -> so esta conta resgata (nao adianta vazar)
      max_redemptions=1      -> uma vez so
      expires_at             -> 7 dias contados agora
      first_time_transaction -> bloqueia quem ja pagou alguma vez
    """
    _, _, _, get_or_create_customer = _lazy()

    ok, motivo = is_eligible_for_welcome(user)
    if not ok:
        print(f"[CUPOM] {user.email} nao elegivel: {motivo}")
        return None

    try:
        customer_id = get_or_create_customer(user)
    except Exception as e:
        print(f"[CUPOM] Falha ao obter customer de {user.email}: {e}")
        return None
    if not customer_id:
        return None

    benef = descrever_beneficio(user)
    expira_em = _now() + timedelta(days=EXPIRY_DAYS)

    ultimo_erro = None
    for tentativa in range(5):
        codigo = _gerar_codigo()
        try:
            promo = stripe.PromotionCode.create(
                coupon=benef['coupon_checkout'],
                code=codigo,
                customer=customer_id,
                max_redemptions=1,
                expires_at=int(expira_em.timestamp()),
                restrictions={'first_time_transaction': True},
                metadata={
                    'app_user_id': str(user.id),
                    'source': 'welcome_campaign',
                    'estrutura': benef['estrutura'],
                },
                idempotency_key=f"welcome_{user.id}_{codigo}",
                stripe_version=STRIPE_API_PROMO,
            )
            print(f"[CUPOM] {codigo} criado para {user.email} "
                  f"({benef['estrutura']}, expira {expira_em:%d/%m/%Y})")
            return {
                'codigo': codigo,
                'promotion_code_id': promo.id,
                'coupon_id': benef['coupon_checkout'],
                'estrutura': benef['estrutura'],
                'pct_mes_1': benef['pct_mes_1'],
                'pct_mes_2_3': benef['pct_mes_2_3'],
                'precisa_complemento': benef['precisa_complemento'],
                'expira_em': expira_em.isoformat(),
                'expira_em_ts': int(expira_em.timestamp()),
            }
        except stripe.InvalidRequestError as e:
            ultimo_erro = e
            if 'already exists' in str(e).lower():
                print(f"[CUPOM] Codigo {codigo} colidiu, sorteando outro...")
                continue
            print(f"[CUPOM] Erro de request: {e}")
            return None
        except Exception as e:
            ultimo_erro = e
            print(f"[CUPOM] Erro inesperado: {e}")
            traceback.print_exc()
            return None

    print(f"[CUPOM] Falhou apos 5 tentativas: {ultimo_erro}")
    return None


def find_promotion_code(codigo: str, customer_id: str) -> Optional[str]:
    """
    Valida um codigo no checkout. So devolve o id se for daquele cliente,
    ativo e dentro do prazo. Usado pela Fase 4b.
    """
    if not codigo:
        return None
    try:
        achados = stripe.PromotionCode.list(
            code=codigo.strip().upper(), limit=5,
            stripe_version=STRIPE_API_PROMO)
    except Exception as e:
        print(f"[CUPOM] Erro ao buscar codigo {codigo}: {e}")
        return None

    agora = int(_now().timestamp())
    for p in achados.data:
        if not p.get('active'):
            continue
        dono = p.get('customer')
        if isinstance(dono, dict):
            dono = dono.get('id')
        if dono and dono != customer_id:
            print(f"[CUPOM] {codigo} pertence a outro cliente. Recusado.")
            continue
        exp = p.get('expires_at')
        if exp and exp < agora:
            print(f"[CUPOM] {codigo} expirado.")
            continue
        return p.id
    return None


# ══════════════════════════════════════════════════════════════════════
# COMPOSICAO — o coracao do modulo
# ══════════════════════════════════════════════════════════════════════

def _cupons_atuais(sub_id: str) -> list[str]:
    """IDs dos cupons ja anexados a assinatura."""
    try:
        sub = stripe.Subscription.retrieve(sub_id, expand=['discounts'])
    except Exception as e:
        print(f"[DESCONTO] Nao foi possivel ler {sub_id}: {e}")
        return []

    ids = []
    for d in (sub.get('discounts') or []):
        if isinstance(d, str):
            try:
                d = stripe.Discount.retrieve(d)
            except Exception:
                continue
        cupom = d.get('coupon') if isinstance(d, dict) else None
        if isinstance(cupom, dict) and cupom.get('id'):
            ids.append(cupom['id'])
        elif isinstance(cupom, str):
            ids.append(cupom)
    return ids


def merge_subscription_discount(sub_id: str, coupon_id: str) -> bool:
    """
    Anexa um cupom PRESERVANDO os que ja estao la.

    Substitui o antigo Subscription.modify(discounts=[novo]), que apagava
    silenciosamente o cupom de boas-vindas dos meses 2 e 3.
    """
    if not sub_id or not coupon_id:
        return False

    atuais = _cupons_atuais(sub_id)
    if coupon_id in atuais:
        print(f"[DESCONTO] {coupon_id} ja esta em {sub_id}. Nada a fazer.")
        return True

    final = atuais + [coupon_id]
    try:
        stripe.Subscription.modify(
            sub_id, discounts=[{'coupon': c} for c in final]
        )
        print(f"[DESCONTO] {sub_id}: {atuais} + {coupon_id} -> {final}")
        return True
    except Exception as e:
        print(f"[DESCONTO] Falha ao anexar {coupon_id} em {sub_id}: {e}")
        traceback.print_exc()
        return False


def maybe_apply_welcome_remainder(user, sub_id: str) -> bool:
    """
    Chamada pelo webhook logo apos a assinatura nascer.

    Quem assinou com o cupom combinado de 20% tem desconto so na 1a
    fatura. Aqui entram os 10% dos meses 2 e 3. Auto-detectavel: le os
    cupons da propria assinatura, sem depender do que veio do checkout.
    """
    if not sub_id:
        return False
    atuais = _cupons_atuais(sub_id)
    if COUPON_WELCOME_REF_1ST not in atuais:
        return False
    if COUPON_WELCOME_REST in atuais:
        print(f"[DESCONTO] Complemento ja aplicado para {user.email}")
        return True
    ok = merge_subscription_discount(sub_id, COUPON_WELCOME_REST)
    if ok:
        print(f"[DESCONTO] {user.email}: 20% no mes 1 + 10% nos meses 2 e 3")
    return ok


def referral_coupon_if_eligible(user) -> Optional[str]:
    """
    Os 10% de quem foi indicado e assina SEM cupom de boas-vindas.

    Sem isto, o indicado que entra direto em /planos nao recebe nada —
    apesar de a tela prometer 'desconto na sua primeira assinatura'.
    Some sozinho depois da 1a assinatura: a indicacao deixa de ser
    'pending' e a funcao passa a devolver None.
    """
    if not has_pending_referral(user):
        return None
    print(f"[DESCONTO] {user.email} foi indicado -> 10% na 1a fatura")
    return COUPON_REFERRAL_ONCE


def apply_welcome_remainder(user, sub_id: str) -> bool:
    """
    Quem assinou com o cupom combinado (20% no mes 1) precisa receber os
    10% dos meses 2 e 3, que nao cabiam na mesma sessao de checkout.
    """
    if not sub_id:
        return False
    if COUPON_WELCOME_REST in _cupons_atuais(sub_id):
        return True
    ok = merge_subscription_discount(sub_id, COUPON_WELCOME_REST)
    if ok:
        print(f"[DESCONTO] Complemento de boas-vindas aplicado para {user.email}")
    return ok


# ══════════════════════════════════════════════════════════════════════
# CLI de diagnostico — nao cria nada
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from auth_service import app, User

    with app.app_context():
        usuarios = User.query.filter(User.role != 'admin').order_by(User.id).all()
        print("=" * 74)
        print(" ELEGIBILIDADE AO CUPOM DE BOAS-VINDAS")
        print("=" * 74)
        elegiveis = 0
        for u in usuarios:
            ok, motivo = is_eligible_for_welcome(u)
            marca = "SIM" if ok else "nao"
            extra = " +indicacao" if (ok and has_pending_referral(u)) else ""
            if ok:
                elegiveis += 1
            print(f" [{marca}] {u.email[:38]:38} {u.page_count or 0:>3}pg  "
                  f"{motivo}{extra}")
        print("=" * 74)
        print(f" {elegiveis} de {len(usuarios)} elegiveis")
        print("=" * 74)
