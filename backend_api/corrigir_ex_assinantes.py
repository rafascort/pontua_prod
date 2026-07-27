#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ex-assinantes que ficaram como 'free' -> 'inactive'. Dry-run por padrao."""
import os, sys
from datetime import datetime
import stripe
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
from auth_service import app, db, User

APLICAR = '--aplicar' in sys.argv
TRIAL = 50


def status_real(u):
    """Devolve o status Stripe se a pessoa REALMENTE assinou e nao esta ativa."""
    if not u.stripe_customer_id:
        return None
    try:
        subs = stripe.Subscription.list(customer=u.stripe_customer_id,
                                        status='all', limit=20)
    except Exception as e:
        print(f"  [erro Stripe] {u.email}: {e}")
        return None
    reais = [s for s in subs.data
             if s.get('status') not in ('incomplete', 'incomplete_expired')]
    if not reais:
        return None
    if [s for s in reais if s.get('status') in ('active', 'trialing')]:
        return None
    return reais[0].get('status')


with app.app_context():
    candidatos = User.query.filter(
        User.plan_status == 'free',
        User.role != 'admin',
        User.organization_id.is_(None),
    ).order_by(User.id).all()

    alvos = []
    for u in candidatos:
        st = status_real(u)
        if st:
            alvos.append((u, st))

    print("=" * 78)
    print(" EX-ASSINANTES COM ACESSO FREE INDEVIDO")
    print("=" * 78)
    if not alvos:
        print(" Nenhuma conta a corrigir.")
        sys.exit(0)

    for u, st in alvos:
        resta = max(0, TRIAL - (u.page_count or 0))
        print(f" id={u.id:<4} {(u.email or '')[:36]:<38} "
              f"{u.page_count or 0:>3}pg  {resta:>2} gratis  Stripe:'{st}'")
    print("-" * 78)

    if not APLICAR:
        print(f" MODO TESTE — nada foi alterado. {len(alvos)} conta(s) seriam")
        print(" mudadas de 'free' para 'inactive' (bloqueadas ate reassinar).")
        print("\n Para efetivar:  python corrigir_ex_assinantes.py --aplicar")
        print("=" * 78)
        sys.exit(0)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rb = f"/opt/pontua/backups/rollback_ex_assinantes_{stamp}.sql"
    with open(rb, "w") as f:
        f.write("-- Rollback: devolve os usuarios ao estado anterior\n")
        for u, _ in alvos:
            f.write(f"UPDATE \"user\" SET plan_status='{u.plan_status}' "
                    f"WHERE id={u.id};  -- {u.email}\n")
    print(f" [ROLLBACK SALVO] {rb}")

    for u, st in alvos:
        u.plan_status = 'inactive'
        print(f"   id={u.id} {u.email} -> inactive")
    try:
        db.session.commit()
        print("-" * 78)
        print(f" {len(alvos)} conta(s) corrigida(s).")
        print(f" Desfazer:  sudo -u postgres psql pontua_db -f {rb}")
    except Exception as e:
        db.session.rollback()
        print(f" [ERRO] {e}")
        sys.exit(1)
    print("=" * 78)
