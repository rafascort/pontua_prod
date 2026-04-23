# /opt/pontua/AutoPonto/backend_api/referral_service.py
"""
Sistema de Indicações — Sistema Ponto v13.2.0 (v2)

Programa permanente de indicação. Independente do sistema de promoções.

Mudanças desta versão (v2):
  - Novo endpoint POST /api/referral/apply-code (aplica código retroativamente)
  - GET /api/referral/stats agora inclui: referred_by_code, referred_by_email_masked, can_change_referrer
  - on_subscription_created agora aplica créditos acumulados do PRÓPRIO usuário
    quando ele faz sua primeira assinatura (resolve caso do usuário free que indica)
  - Permite trocar código enquanto não é assinante pago

Lógica:
  - Cada usuário tem um `referral_code` único gerado no cadastro
  - 10% de desconto por cada indicação convertida (cap 40%/mês)
  - Excedente acumula em `discount_credits` para o mês seguinte (distribuído)
  - Conversão disparada quando o indicado assina um plano pago (webhook Stripe)
  - Código pode ser aplicado até a PRIMEIRA assinatura paga

Convenção: o módulo NÃO cria o `app`; ele recebe referências do auth_service.py.
"""
from __future__ import annotations

import os
import re
import secrets
import string
import traceback
from datetime import datetime, timezone
from typing import Optional
from functools import wraps

import stripe
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from sqlalchemy import func


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_CODE_LENGTH = 8
REFERRAL_PCT_PER_CONVERSION = 10
REFERRAL_MAX_PCT_PER_MONTH = 40

# Deve bater com os planos pagos definidos em queue_manager.PAID_PLANS
ACTIVE_PAID_PLANS = {"basic", "standard", "premium"}


# ═══════════════════════════════════════════════════════════════════════════
# REFERÊNCIAS GLOBAIS (preenchidas por init_referral_routes)
# ═══════════════════════════════════════════════════════════════════════════

_app = None
_db = None
_User = None
_Referral = None


# ═══════════════════════════════════════════════════════════════════════════
# DECORATOR admin_required
# ═══════════════════════════════════════════════════════════════════════════

def _admin_required():
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') == 'admin':
                return fn(*args, **kwargs)
            return jsonify(msg="Acesso restrito a administradores!"), 403
        return decorator
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _mask_email(email: str) -> str:
    """Mascara email: 'joao@gmail.com' → 'jo***@gmail.com'"""
    if not email or '@' not in email:
        return email or ''
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        return f"{name[0]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def generate_referral_code(user_email: str) -> str:
    """Gera código único baseado no prefixo do email + sufixo aleatório."""
    prefix = re.sub(r'[^A-Z]', '', user_email.split('@')[0].upper())[:3] or 'USR'
    for _ in range(10):
        suffix = ''.join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(5))
        candidate = f"{prefix}{suffix}"
        if not _User.query.filter_by(referral_code=candidate).first():
            return candidate
    return ''.join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


def ensure_user_has_referral_code(user) -> str:
    """Garante que o usuário tenha um código gerado."""
    if not user.referral_code:
        user.referral_code = generate_referral_code(user.email)
        try:
            _db.session.commit()
        except Exception as e:
            _db.session.rollback()
            print(f"[REFERRAL] Erro ao salvar código para {user.email}: {e}")
            raise
    return user.referral_code


def _user_is_paid_subscriber(user) -> bool:
    """True se o usuário é assinante ativo de um plano pago."""
    return (user.plan_status or '').lower() in ACTIVE_PAID_PLANS


# ═══════════════════════════════════════════════════════════════════════════
# CAPTURA NO /api/register (chamado pelo auth_service.py)
# ═══════════════════════════════════════════════════════════════════════════

def process_referral_on_signup(new_user, ref_code: Optional[str]) -> bool:
    """
    Chamado pelo /api/register após criar o usuário.
    Valida o código, bloqueia auto-indicação, salva vínculo pendente.
    """
    if not ref_code:
        return False

    ref_code = ref_code.strip().upper()
    referrer = _User.query.filter_by(referral_code=ref_code).first()

    if not referrer:
        print(f"[REFERRAL] Código inválido recebido no cadastro: {ref_code}")
        return False

    if referrer.email.lower() == new_user.email.lower() or referrer.id == new_user.id:
        print(f"[REFERRAL] Auto-indicação bloqueada: {new_user.email}")
        return False

    new_user.referred_by_code = ref_code
    try:
        _db.session.commit()
        pending = _Referral(
            referrer_id=referrer.id,
            referred_id=new_user.id,
            referrer_code=ref_code,
            status='pending',
            created_at=datetime.now(timezone.utc),
        )
        _db.session.add(pending)
        _db.session.commit()
        print(f"[REFERRAL] Vínculo criado: {new_user.email} referido por {referrer.email} ({ref_code})")
        return True
    except Exception as e:
        _db.session.rollback()
        print(f"[REFERRAL] Erro ao salvar vínculo: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSÃO — DISPARADA PELO WEBHOOK DO STRIPE
# ═══════════════════════════════════════════════════════════════════════════

def on_subscription_created(user, subscription) -> None:
    """
    Chamado quando QUALQUER assinatura é criada/confirmada no Stripe.

    Faz DUAS coisas:
      1. Se o usuário foi indicado por alguém, marca a indicação como convertida
         e dá 1 crédito ao indicador
      2. Se o próprio usuário tem créditos acumulados (ex: ele é free que indicou
         outros antes de assinar), aplica o desconto na própria assinatura
    """
    # ── Parte 1: conversão da indicação (crédito para o indicador) ──
    _convert_pending_referral(user, subscription)

    # ── Parte 2: aplicar créditos acumulados do PRÓPRIO usuário ──
    _apply_own_accumulated_credits(user)


def _convert_pending_referral(user, subscription) -> None:
    """Parte 1: se user foi indicado, converte a referral e credita o indicador."""
    if not user.referred_by_code:
        return

    referral = _Referral.query.filter_by(
        referred_id=user.id,
        status='pending',
    ).first()

    if not referral:
        return

    referrer = _User.query.get(referral.referrer_id)
    if not referrer:
        print(f"[REFERRAL] Indicador id={referral.referrer_id} não encontrado")
        return

    plan_name = _extract_plan_name_from_subscription(subscription)
    if plan_name not in ACTIVE_PAID_PLANS:
        print(f"[REFERRAL] Plano '{plan_name}' não é pago — ignorando conversão de {user.email}")
        return

    referral.status = 'converted'
    referral.plan_at_conversion = plan_name
    referral.discount_granted_pct = REFERRAL_PCT_PER_CONVERSION
    referral.converted_at = datetime.now(timezone.utc)

    referrer.discount_credits = (referrer.discount_credits or 0) + 1

    try:
        _db.session.commit()
        print(f"[REFERRAL] ✓ Conversão: {user.email} → crédito para {referrer.email} "
              f"(agora {referrer.discount_credits} créditos)")
    except Exception as e:
        _db.session.rollback()
        print(f"[REFERRAL] Erro ao commitar conversão: {e}")
        return

    # Tenta aplicar desconto imediatamente se o indicador já for assinante ativo
    if _user_is_paid_subscriber(referrer):
        try:
            apply_discount_to_next_invoice(referrer)
        except Exception as e:
            print(f"[REFERRAL] Erro ao aplicar cupom Stripe para {referrer.email}: {e}")
            traceback.print_exc()
    else:
        print(f"[REFERRAL] {referrer.email} não é assinante ativo — "
              f"crédito aguarda próxima assinatura")


def _apply_own_accumulated_credits(user) -> None:
    """Parte 2: se o user tem créditos acumulados, aplica na assinatura própria."""
    if (user.discount_credits or 0) <= 0:
        return

    if not _user_is_paid_subscriber(user):
        print(f"[REFERRAL] {user.email} tem créditos mas não tem plano pago ativo — "
              f"plan_status={user.plan_status}")
        return

    try:
        result = apply_discount_to_next_invoice(user)
        if result:
            print(f"[REFERRAL] Créditos acumulados aplicados para {user.email}: "
                  f"{result['percent_off']}% na próxima fatura")
    except Exception as e:
        print(f"[REFERRAL] Erro ao aplicar créditos acumulados de {user.email}: {e}")
        traceback.print_exc()


def _extract_plan_name_from_subscription(subscription) -> str:
    """Extrai o plano a partir de uma assinatura Stripe."""
    try:
        from auth_service import PRICE_ID_TO_PLAN_NAME, PLAN_NAME_TO_EXTRA_PRICE_ID
    except ImportError:
        return 'unknown'

    items = subscription.get('items', {}).get('data', [])

    # 1. Procura pelo preço base (não medido)
    for item in items:
        price = item.get('price', {}) or {}
        price_id = price.get('id')
        recurring = price.get('recurring', {}) or {}
        if recurring.get('usage_type') != 'metered':
            plan = PRICE_ID_TO_PLAN_NAME.get(price_id)
            if plan:
                return plan

    # 2. Fallback: tenta encontrar pelo preço extra (páginas medidas)
    for item in items:
        price_id = (item.get('price') or {}).get('id')
        for plan, extra_id in PLAN_NAME_TO_EXTRA_PRICE_ID.items():
            if extra_id == price_id:
                return plan

    return 'unknown'


# ═══════════════════════════════════════════════════════════════════════════
# APLICAÇÃO DE DESCONTO
# ═══════════════════════════════════════════════════════════════════════════

def compute_discount_for_next_invoice(user) -> int:
    """Calcula o % de desconto a aplicar na próxima fatura (até o cap)."""
    credits = user.discount_credits or 0
    if credits <= 0:
        return 0
    max_credits_per_month = REFERRAL_MAX_PCT_PER_MONTH // REFERRAL_PCT_PER_CONVERSION
    return min(credits, max_credits_per_month) * REFERRAL_PCT_PER_CONVERSION


def apply_discount_to_next_invoice(user) -> Optional[dict]:
    """
    Cria cupom Stripe (one-time) e anexa à assinatura ativa do usuário.
    Só faz sentido para usuários que JÁ são assinantes.
    """
    if not user.stripe_customer_id:
        return None

    pct = compute_discount_for_next_invoice(user)
    if pct <= 0:
        return None

    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id,
            status='active',
            limit=1,
        )
        if not subs.data:
            print(f"[REFERRAL] {user.email} sem assinatura ativa — crédito aguarda próxima assinatura")
            return None
        sub = subs.data[0]
    except Exception as e:
        print(f"[REFERRAL] Erro ao buscar assinatura de {user.email}: {e}")
        return None

    try:
        coupon = stripe.Coupon.create(
            percent_off=pct,
            duration='once',
            name=f"Indicações Sistema Ponto ({pct}%)",
            metadata={
                'app_user_id': user.id,
                'source': 'referral_system',
            },
        )
        print(f"[REFERRAL] Cupom criado: {coupon.id} ({pct}% off) para {user.email}")
    except Exception as e:
        print(f"[REFERRAL] Erro ao criar cupom: {e}")
        return None

    try:
        stripe.Subscription.modify(
            sub.id,
            discounts=[{'coupon': coupon.id}],
        )
        print(f"[REFERRAL] Cupom anexado à assinatura {sub.id}")
    except Exception as e:
        print(f"[REFERRAL] Erro ao anexar cupom: {e}")
        return None

    return {
        'coupon_id': coupon.id,
        'percent_off': pct,
    }


def on_invoice_paid_consume_credits(user, invoice) -> None:
    """
    Consome créditos após pagamento de fatura mensal.
    Se ainda houver créditos, re-aplica cupom para o próximo ciclo.
    """
    discount_amounts = invoice.get('total_discount_amounts') or []
    if not discount_amounts:
        return

    credits_before = user.discount_credits or 0
    max_credits_per_month = REFERRAL_MAX_PCT_PER_MONTH // REFERRAL_PCT_PER_CONVERSION
    credits_consumed = min(credits_before, max_credits_per_month)

    if credits_consumed > 0:
        user.discount_credits = credits_before - credits_consumed
        try:
            _db.session.commit()
            print(f"[REFERRAL] {user.email}: consumiu {credits_consumed} crédito(s), "
                  f"restam {user.discount_credits}")
        except Exception as e:
            _db.session.rollback()
            print(f"[REFERRAL] Erro ao decrementar créditos: {e}")
            return

    if (user.discount_credits or 0) > 0:
        try:
            apply_discount_to_next_invoice(user)
        except Exception as e:
            print(f"[REFERRAL] Erro ao re-aplicar cupom: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DO USUÁRIO
# ═══════════════════════════════════════════════════════════════════════════

def register_user_endpoints(app):

    @app.route('/api/referral/stats', methods=['GET'])
    @jwt_required()
    def referral_stats():
        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()
        if not user:
            return jsonify({"msg": "Usuário não encontrado"}), 404

        code = ensure_user_has_referral_code(user)

        converted = _Referral.query.filter_by(
            referrer_id=user.id, status='converted'
        ).count()
        pending = _Referral.query.filter_by(
            referrer_id=user.id, status='pending'
        ).count()

        active_pct = compute_discount_for_next_invoice(user)
        max_credits_per_month = REFERRAL_MAX_PCT_PER_MONTH // REFERRAL_PCT_PER_CONVERSION
        extra_credits = max(0, (user.discount_credits or 0) - max_credits_per_month)
        next_month_pct = extra_credits * REFERRAL_PCT_PER_CONVERSION

        frontend_url = os.getenv('FRONTEND_URL', 'https://sistemaponto.com')
        full_link = f"{frontend_url}/cadastro?ref={code}"

        # ── v2: Informações sobre quem indicou o usuário atual ──
        referred_by_email_masked = None
        if user.referred_by_code:
            referrer_user = _User.query.filter_by(
                referral_code=user.referred_by_code
            ).first()
            if referrer_user:
                referred_by_email_masked = _mask_email(referrer_user.email)

        can_change_referrer = not _user_is_paid_subscriber(user)

        return jsonify({
            'referral_code': code,
            'referral_link': full_link,
            'converted_count': converted,
            'pending_count': pending,
            'discount_credits': user.discount_credits or 0,
            'active_discount_pct': active_pct,
            'next_month_discount_pct': next_month_pct,
            'max_monthly_discount_pct': REFERRAL_MAX_PCT_PER_MONTH,
            'pct_per_conversion': REFERRAL_PCT_PER_CONVERSION,
            # ── v2 ──
            'referred_by_code': user.referred_by_code,
            'referred_by_email_masked': referred_by_email_masked,
            'can_change_referrer': can_change_referrer,
        }), 200

    @app.route('/api/referral/history', methods=['GET'])
    @jwt_required()
    def referral_history():
        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()
        if not user:
            return jsonify({"msg": "Usuário não encontrado"}), 404

        refs = (
            _Referral.query.filter_by(referrer_id=user.id)
            .order_by(_Referral.created_at.desc())
            .all()
        )

        result = []
        for r in refs:
            referred = _User.query.get(r.referred_id)
            result.append({
                'id': r.id,
                'referred_email_masked': _mask_email(referred.email if referred else ''),
                'status': r.status,
                'plan': r.plan_at_conversion,
                'discount_pct': r.discount_granted_pct,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'converted_at': r.converted_at.isoformat() if r.converted_at else None,
            })
        return jsonify({'referrals': result}), 200

    # ═══ v2: NOVO ENDPOINT — aplicar código retroativamente ═══
    @app.route('/api/referral/apply-code', methods=['POST'])
    @jwt_required()
    def apply_referral_code_endpoint():
        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()
        if not user:
            return jsonify({"msg": "Usuário não encontrado"}), 404

        data = request.get_json() or {}
        code = (data.get('code') or '').strip().upper()

        if not code or len(code) < 3:
            return jsonify({"msg": "Informe um código válido."}), 400

        # Regra: não pode aplicar se já é assinante pago
        if _user_is_paid_subscriber(user):
            return jsonify({
                "msg": "Códigos de indicação só podem ser aplicados antes da primeira assinatura paga.",
                "error_code": "ALREADY_PAID_SUBSCRIBER",
            }), 400

        # Buscar o indicador pelo código
        referrer = _User.query.filter_by(referral_code=code).first()
        if not referrer:
            return jsonify({
                "msg": "Código não encontrado. Verifique com quem te indicou.",
                "error_code": "CODE_NOT_FOUND",
            }), 404

        # Regra: não pode ser auto-indicação
        if referrer.id == user.id:
            return jsonify({
                "msg": "Você não pode usar seu próprio código.",
                "error_code": "SELF_REFERRAL",
            }), 400

        # Se já tem o mesmo código aplicado, não faz nada
        if user.referred_by_code == code:
            return jsonify({
                "msg": "Este código já está aplicado na sua conta.",
                "referred_by_code": code,
                "referred_by_email_masked": _mask_email(referrer.email),
            }), 200

        # Se tem código diferente, DELETA o vínculo pendente antigo (troca)
        if user.referred_by_code and user.referred_by_code != code:
            old_refs = _Referral.query.filter_by(
                referred_id=user.id,
                status='pending',
            ).all()
            for old in old_refs:
                _db.session.delete(old)
            print(f"[REFERRAL] {user.email} trocou código: {user.referred_by_code} → {code}")

        # Aplica o novo código
        user.referred_by_code = code
        new_referral = _Referral(
            referrer_id=referrer.id,
            referred_id=user.id,
            referrer_code=code,
            status='pending',
            created_at=datetime.now(timezone.utc),
        )
        _db.session.add(new_referral)

        try:
            _db.session.commit()
            print(f"[REFERRAL] ✓ Código {code} aplicado retroativamente para {user.email} "
                  f"(indicador: {referrer.email})")
            return jsonify({
                "msg": "Código aplicado com sucesso. O desconto será aplicado na sua primeira assinatura.",
                "referred_by_code": code,
                "referred_by_email_masked": _mask_email(referrer.email),
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[REFERRAL] Erro ao aplicar código retroativo: {e}")
            return jsonify({"msg": "Erro ao aplicar código. Tente novamente."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE ADMINISTRAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def register_admin_endpoints(app):

    @app.route('/api/admin/referrals', methods=['GET'])
    @_admin_required()
    def admin_list_referrals():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status', '', type=str)
        search = request.args.get('search', '', type=str)

        query = _Referral.query
        if status_filter and status_filter != 'all':
            query = query.filter(_Referral.status == status_filter)

        if search:
            like = f"%{search}%"
            user_ids = [u.id for u in _User.query.filter(_User.email.ilike(like)).all()]
            query = query.filter(
                (_Referral.referrer_id.in_(user_ids)) |
                (_Referral.referred_id.in_(user_ids))
            )

        query = query.order_by(_Referral.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        items = []
        for r in pagination.items:
            referrer = _User.query.get(r.referrer_id)
            referred = _User.query.get(r.referred_id)
            items.append({
                'id': r.id,
                'referrer_id': r.referrer_id,
                'referrer_email': referrer.email if referrer else '(excluído)',
                'referrer_code': r.referrer_code,
                'referred_id': r.referred_id,
                'referred_email': referred.email if referred else '(excluído)',
                'referred_plan_status': referred.plan_status if referred else None,
                'status': r.status,
                'plan_at_conversion': r.plan_at_conversion,
                'discount_granted_pct': r.discount_granted_pct,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'converted_at': r.converted_at.isoformat() if r.converted_at else None,
            })

        stats = {
            'total': _Referral.query.count(),
            'converted': _Referral.query.filter_by(status='converted').count(),
            'pending': _Referral.query.filter_by(status='pending').count(),
            'total_discount_pct_distributed': _db.session.query(
                func.coalesce(func.sum(_Referral.discount_granted_pct), 0)
            ).scalar() or 0,
        }

        return jsonify({
            'items': items,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page,
            'stats': stats,
        }), 200

    @app.route('/api/admin/referrers', methods=['GET'])
    @_admin_required()
    def admin_list_referrers():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        rows = _db.session.query(
            _User.id,
            _User.email,
            _User.referral_code,
            _User.discount_credits,
            _User.plan_status,
            func.count(_Referral.id).filter(_Referral.status == 'converted').label('converted'),
            func.count(_Referral.id).filter(_Referral.status == 'pending').label('pending'),
            func.count(_Referral.id).label('total'),
        ).outerjoin(
            _Referral, _Referral.referrer_id == _User.id
        ).group_by(
            _User.id
        ).having(
            func.count(_Referral.id) > 0
        ).order_by(
            func.count(_Referral.id).filter(_Referral.status == 'converted').desc()
        )

        total = rows.count()
        items_raw = rows.offset((page - 1) * per_page).limit(per_page).all()

        max_credits_per_month = REFERRAL_MAX_PCT_PER_MONTH // REFERRAL_PCT_PER_CONVERSION

        items = []
        for r in items_raw:
            credits = r.discount_credits or 0
            active_pct = min(credits, max_credits_per_month) * REFERRAL_PCT_PER_CONVERSION
            next_month_pct = max(0, credits - max_credits_per_month) * REFERRAL_PCT_PER_CONVERSION
            items.append({
                'user_id': r.id,
                'email': r.email,
                'referral_code': r.referral_code,
                'plan_status': r.plan_status,
                'converted_count': r.converted or 0,
                'pending_count': r.pending or 0,
                'total_count': r.total or 0,
                'discount_credits': credits,
                'active_discount_pct': active_pct,
                'next_month_discount_pct': next_month_pct,
            })

        return jsonify({
            'items': items,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
            'current_page': page,
        }), 200


# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def init_referral_routes(app, db, User):
    """Registra modelos e endpoints. Chamada do auth_service.py."""
    global _app, _db, _User, _Referral
    _app = app
    _db = db
    _User = User

    class Referral(db.Model):
        __tablename__ = 'referral'
        id = db.Column(db.Integer, primary_key=True)
        referrer_id = db.Column(db.Integer,
                                db.ForeignKey('user.id', ondelete='CASCADE'),
                                nullable=False, index=True)
        referred_id = db.Column(db.Integer,
                                db.ForeignKey('user.id', ondelete='CASCADE'),
                                nullable=False, unique=True)
        referrer_code = db.Column(db.String(20), nullable=False)
        status = db.Column(db.String(20), nullable=False, default='pending', index=True)
        plan_at_conversion = db.Column(db.String(50), nullable=True)
        discount_granted_pct = db.Column(db.Integer, nullable=False, default=0)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        converted_at = db.Column(db.DateTime, nullable=True)
        credit_applied = db.Column(db.Boolean, nullable=False, default=False)

    _Referral = Referral

    register_user_endpoints(app)
    register_admin_endpoints(app)

    print("[REFERRAL] Módulo de indicações carregado (v2 — retroativo + créditos acumulados).")
    return Referral
