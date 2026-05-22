# backend_api/stripe_org_service.py
"""
Operacoes Stripe para empresas (multi-tenancy).

Funcoes expostas:
  - find_entity_by_stripe_customer_id(customer_id) -> ('organization'|'user'|None, entity|None)
  - create_or_get_org_customer(org) -> stripe_customer_id
  - create_metered_price_for_org(org) -> stripe_price_id
  - create_checkout_session_for_org(org) -> checkout_url
  - apply_pending_price_change(org) -> bool
  - check_org_can_process(user) -> (True, None) | (False, (resp, status))
  - report_org_usage_to_stripe(user, pages) -> None
  - route_org_webhook_if_applicable(event) -> bool
  - cancel_org_subscription(org) -> bool

Imports tardios (de auth_service) para evitar circular import.
"""

import os
import traceback

import stripe
from flask import jsonify


# Statuses "saudaveis" da subscription Stripe
PAID_STATUSES = ('active', 'past_due')

# Cache do meter_id (busca uma vez por processo)
_cached_meter_id = None


# ═══════════════════════════════════════════════════════════════════════
# HELPERS GERAIS
# ═══════════════════════════════════════════════════════════════════════

def _get_meter_id():
    """Busca o meter_id no Stripe pelo event_name (cache em memoria)."""
    global _cached_meter_id
    if _cached_meter_id:
        return _cached_meter_id

    event_name = os.getenv('STRIPE_METER_ENTERPRISE', 'pagina_empresa')
    meters = stripe.billing.Meter.list(limit=100)
    for m in meters.data:
        if m.event_name == event_name:
            _cached_meter_id = m.id
            print(f"[ORG-STRIPE] Meter '{event_name}' resolvido: {m.id}")
            return m.id
    raise RuntimeError(
        f"Meter com event_name='{event_name}' nao existe no Stripe. "
        f"Crie em Dashboard -> Billing -> Meters."
    )


def find_entity_by_stripe_customer_id(stripe_customer_id):
    """
    Retorna ('organization', org) | ('user', user) | (None, None).
    Empresa tem prioridade.
    """
    from auth_service import Organization, User

    if not stripe_customer_id:
        return (None, None)

    org = _safe_org_lookup_by_customer(Organization, stripe_customer_id)
    if org:
        return ('organization', org)

    user = User.query.filter_by(stripe_customer_id=stripe_customer_id).first()
    if user:
        return ('user', user)

    return (None, None)


def _safe_org_lookup_by_customer(Organization, customer_id):
    try:
        return Organization.query.filter_by(stripe_customer_id=customer_id).first()
    except Exception as e:
        print(f"[ORG-STRIPE] Erro lookup org por customer_id: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# CRIACAO DE CUSTOMER, PRICE E CHECKOUT
# ═══════════════════════════════════════════════════════════════════════

def create_or_get_org_customer(org):
    """Cria Stripe Customer da empresa se ainda nao tiver."""
    from auth_service import db

    if org.stripe_customer_id:
        return org.stripe_customer_id

    customer = stripe.Customer.create(
        email=org.billing_email,
        name=org.name,
        metadata={
            'organization_id': str(org.id),
            'cnpj': org.cnpj or '',
            'kind': 'enterprise',
        },
    )
    org.stripe_customer_id = customer.id
    db.session.commit()
    print(f"[ORG-STRIPE] Customer criado empresa #{org.id}: {customer.id}")
    return customer.id


def create_metered_price_for_org(org):
    """Cria Price metered BRL on-demand para a empresa."""
    from auth_service import db

    product_id = os.getenv('STRIPE_PRODUCT_ID_ENTERPRISE')
    if not product_id:
        raise RuntimeError("STRIPE_PRODUCT_ID_ENTERPRISE nao configurado.")

    meter_id = _get_meter_id()

    price = stripe.Price.create(
        currency='brl',
        unit_amount=org.price_per_page_cents,
        recurring={
            'interval': 'month',
            'usage_type': 'metered',
            'meter': meter_id,
        },
        product=product_id,
        nickname=f"Org #{org.id} - R$ {org.price_per_page_cents/100:.2f}/pag",
        metadata={
            'organization_id': str(org.id),
            'price_per_page_cents': str(org.price_per_page_cents),
        },
    )
    org.stripe_price_id = price.id
    db.session.commit()
    print(f"[ORG-STRIPE] Price criado empresa #{org.id}: {price.id} "
          f"(R$ {org.price_per_page_cents/100:.2f}/pag)")
    return price.id


def create_checkout_session_for_org(org):
    """Cria Checkout Session do Stripe para a empresa cadastrar cartao."""
    customer_id = create_or_get_org_customer(org)
    if not org.stripe_price_id:
        create_metered_price_for_org(org)

    frontend = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode='subscription',
        line_items=[{'price': org.stripe_price_id}],  # sem quantity (metered)
        success_url=f"{frontend}/empresa/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{frontend}/empresa?checkout=canceled",
        metadata={
            'organization_id': str(org.id),
            'purpose': 'enterprise_initial_setup',
        },
        subscription_data={
            'metadata': {
                'organization_id': str(org.id),
                'kind': 'enterprise',
            },
        },
    )
    print(f"[ORG-STRIPE] Checkout session empresa #{org.id}: {session.id}")
    return session.url


# ═══════════════════════════════════════════════════════════════════════
# SWAP DE PRECO NO FECHAMENTO DO CICLO
# ═══════════════════════════════════════════════════════════════════════

def apply_pending_price_change(org):
    """
    Se org.pending_price_per_page_cents difere do vigente, cria novo Price 
    e atualiza o subscription_item. Chamado no webhook invoice.payment_succeeded 
    com billing_reason='subscription_cycle'.
    """
    from auth_service import db

    pending = org.pending_price_per_page_cents
    if not pending:
        return False
    if pending == org.price_per_page_cents:
        org.pending_price_per_page_cents = None
        db.session.commit()
        return False
    if not org.stripe_subscription_id:
        print(f"[ORG-STRIPE] Empresa #{org.id} sem subscription, swap abortado.")
        return False

    product_id = os.getenv('STRIPE_PRODUCT_ID_ENTERPRISE')
    meter_id = _get_meter_id()

    # 1. Novo Price
    new_price = stripe.Price.create(
        currency='brl',
        unit_amount=pending,
        recurring={
            'interval': 'month',
            'usage_type': 'metered',
            'meter': meter_id,
        },
        product=product_id,
        nickname=f"Org #{org.id} - R$ {pending/100:.2f}/pag (renegociado)",
        metadata={
            'organization_id': str(org.id),
            'price_per_page_cents': str(pending),
            'previous_price_id': org.stripe_price_id or '',
        },
    )

    # 2. Troca subscription_item
    sub = stripe.Subscription.retrieve(org.stripe_subscription_id)
    items = sub.get('items', {}).get('data', [])
    if not items:
        print(f"[ORG-STRIPE] Subscription {org.stripe_subscription_id} sem items.")
        return False

    stripe.SubscriptionItem.modify(items[0]['id'], price=new_price.id)

    # 3. Atualiza empresa
    old_price = org.price_per_page_cents
    org.price_per_page_cents = pending
    org.pending_price_per_page_cents = None
    org.stripe_price_id = new_price.id
    db.session.commit()

    print(f"[ORG-STRIPE] Preco empresa #{org.id}: "
          f"R$ {old_price/100:.2f} -> R$ {pending/100:.2f}/pag. "
          f"Novo Price: {new_price.id}")
    return True


# ═══════════════════════════════════════════════════════════════════════
# HELPERS USADOS POR queue_manager.py
# ═══════════════════════════════════════════════════════════════════════

def check_org_can_process(user):
    """Retorna (True, None) ou (False, (jsonify_resp, status))."""
    from auth_service import Organization

    org = Organization.query.get(user.organization_id)
    if not org:
        return False, (jsonify({"error": "Empresa nao encontrada."}), 403)

    if not org.is_active:
        return False, (jsonify({
            "error": "Empresa inativa.",
            "detail": "Sua empresa foi desativada. Contate o admin da empresa.",
        }), 403)

    if org.plan_status == 'awaiting_setup':
        return False, (jsonify({
            "error": "Empresa aguardando configuracao.",
            "detail": "A empresa ainda nao tem cartao cadastrado. "
                      "Avise o admin da empresa para finalizar o cadastro.",
        }), 403)

    if org.plan_status == 'past_due':
        return False, (jsonify({
            "error": "Pagamento pendente.",
            "detail": "A empresa tem pagamento pendente. "
                      "Avise o admin da empresa para regularizar.",
        }), 403)

    if org.plan_status in ('suspended', 'inactive'):
        return False, (jsonify({
            "error": "Empresa suspensa.",
            "detail": "Sua empresa esta suspensa. Contate o admin da empresa.",
        }), 403)

    if org.plan_status == 'active':
        return True, None

    return False, (jsonify({
        "error": f"Status da empresa desconhecido: {org.plan_status}",
    }), 403)


def report_org_usage_to_stripe(user, pages_processed):
    """Incrementa org.page_count e dispara MeterEvent."""
    from auth_service import db, Organization

    if pages_processed <= 0:
        return

    org = Organization.query.get(user.organization_id)
    if not org:
        print(f"[ORG ERRO] Empresa #{user.organization_id} nao achada (report).")
        return

    # Incrementa contagem agregada
    try:
        org.page_count = (org.page_count or 0) + pages_processed
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG ERRO] page_count empresa #{org.id}: {e}")

    if not org.stripe_customer_id:
        print(f"[ORG WARN] Empresa #{org.id} sem stripe_customer_id; "
              f"pags contadas localmente (+{pages_processed}). "
              f"Total: {org.page_count}")
        return

    # Reporta meter event
    try:
        event_name = os.getenv('STRIPE_METER_ENTERPRISE', 'pagina_empresa')
        stripe.billing.MeterEvent.create(
            event_name=event_name,
            payload={
                'stripe_customer_id': org.stripe_customer_id,
                'value': str(pages_processed),
            },
        )
        print(f"[ORG] +{pages_processed} pags reportadas empresa "
              f"#{org.id} ({org.name}). Total ciclo: {org.page_count}.")
    except Exception as e:
        print(f"[ORG ERRO] MeterEvent empresa #{org.id}: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════
# HANDLERS DE WEBHOOK
# ═══════════════════════════════════════════════════════════════════════

def _handle_org_invoice_payment_succeeded(org, invoice):
    from auth_service import db

    billing_reason = invoice.get('billing_reason', '')
    invoice_id = invoice.get('id', '')
    print(f"[ORG-WEBHOOK] invoice.paid empresa #{org.id} reason={billing_reason} "
          f"invoice={invoice_id}")

    try:
        # Ativa empresa se estiver pendente
        if org.plan_status in ('awaiting_setup', 'past_due', 'suspended'):
            org.plan_status = 'active'
            org.is_active = True

        sub_id = invoice.get('subscription')
        if sub_id and not org.stripe_subscription_id:
            org.stripe_subscription_id = sub_id

        # Renovacao de ciclo: zera contador e aplica preco pendente
        if billing_reason == 'subscription_cycle':
            old_count = org.page_count
            org.page_count = 0
            db.session.commit()
            print(f"[ORG-WEBHOOK] page_count empresa #{org.id}: "
                  f"{old_count} -> 0")

            if org.pending_price_per_page_cents:
                apply_pending_price_change(org)
            return

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] invoice_paid empresa #{org.id}: {e}")
        traceback.print_exc()


def _handle_org_invoice_payment_failed(org, invoice):
    from auth_service import db
    print(f"[ORG-WEBHOOK] invoice.failed empresa #{org.id}")
    try:
        org.plan_status = 'past_due'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] invoice_failed empresa #{org.id}: {e}")


def _handle_org_subscription_created(org, subscription):
    from auth_service import db
    print(f"[ORG-WEBHOOK] sub.created empresa #{org.id}: {subscription.get('id')}")
    try:
        org.stripe_subscription_id = subscription.get('id')
        if subscription.get('status') in PAID_STATUSES:
            org.plan_status = 'active'
            org.is_active = True
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] sub_created empresa #{org.id}: {e}")


def _handle_org_subscription_updated(org, subscription):
    from auth_service import db
    status = subscription.get('status', '')
    print(f"[ORG-WEBHOOK] sub.updated empresa #{org.id}: status={status}")
    try:
        if status == 'active':
            org.plan_status = 'active'
            org.is_active = True
        elif status == 'past_due':
            org.plan_status = 'past_due'
        elif status in ('canceled', 'unpaid', 'incomplete_expired'):
            org.plan_status = 'inactive'
            org.is_active = False
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] sub_updated empresa #{org.id}: {e}")


def _handle_org_subscription_deleted(org, subscription):
    from auth_service import db
    print(f"[ORG-WEBHOOK] sub.deleted empresa #{org.id}")
    try:
        org.plan_status = 'inactive'
        org.is_active = False
        org.stripe_subscription_id = None
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] sub_deleted empresa #{org.id}: {e}")


def _handle_org_checkout_completed(org, session):
    from auth_service import db
    print(f"[ORG-WEBHOOK] checkout.completed empresa #{org.id}: {session.get('id')}")
    try:
        if session.get('mode') == 'subscription' and session.get('subscription'):
            org.stripe_subscription_id = session.get('subscription')
            org.plan_status = 'active'
            org.is_active = True
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ORG-WEBHOOK ERRO] checkout empresa #{org.id}: {e}")


def route_org_webhook_if_applicable(event):
    """
    Roteia evento Stripe para handler de empresa se o customer for organization.
    Retorna True se foi roteado (caller deve retornar), False se nao.
    """
    if not event:
        return False

    obj = event.get('data', {}).get('object', {}) or {}
    event_type = event.get('type', '')

    # customer pode estar em campos diferentes dependendo do tipo de evento
    customer_id = (
        obj.get('customer')
        or obj.get('customer_id')
        or (obj.get('subscription_details', {}) or {}).get('metadata', {}).get('customer')
    )
    if not customer_id:
        return False

    kind, entity = find_entity_by_stripe_customer_id(customer_id)
    if kind != 'organization':
        return False

    print(f"[ORG-WEBHOOK ROUTE] {event_type} -> empresa #{entity.id}")

    try:
        if event_type == 'invoice.payment_succeeded':
            _handle_org_invoice_payment_succeeded(entity, obj)
        elif event_type == 'invoice.payment_failed':
            _handle_org_invoice_payment_failed(entity, obj)
        elif event_type == 'customer.subscription.created':
            _handle_org_subscription_created(entity, obj)
        elif event_type == 'customer.subscription.updated':
            _handle_org_subscription_updated(entity, obj)
        elif event_type == 'customer.subscription.deleted':
            _handle_org_subscription_deleted(entity, obj)
        elif event_type == 'checkout.session.completed':
            _handle_org_checkout_completed(entity, obj)
        else:
            print(f"[ORG-WEBHOOK] tipo nao tratado: {event_type}")
    except Exception as e:
        print(f"[ORG-WEBHOOK ERRO] {event_type} empresa #{entity.id}: {e}")
        traceback.print_exc()

    return True


# ═══════════════════════════════════════════════════════════════════════
# CANCELAMENTO
# ═══════════════════════════════════════════════════════════════════════

def cancel_org_subscription(org):
    from auth_service import db

    if not org.stripe_subscription_id:
        return False
    try:
        stripe.Subscription.delete(org.stripe_subscription_id)
        org.plan_status = 'inactive'
        org.is_active = False
        org.stripe_subscription_id = None
        db.session.commit()
        print(f"[ORG-STRIPE] Subscription empresa #{org.id} cancelada.")
        return True
    except Exception as e:
        print(f"[ORG-STRIPE ERRO] cancel empresa #{org.id}: {e}")
        return False


print("[ORG-STRIPE] Modulo Stripe Empresas carregado.")
