#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raio-X da base — somente leitura. Nao altera banco nem Stripe."""
import os
import stripe
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

from auth_service import app, db, User, EmailEvent

PAGOS = {'basic', 'standard', 'premium'}
TRIAL = 50


def ver_stripe(u):
    if not u.stripe_customer_id:
        return 'sem cadastro', False
    try:
        subs = stripe.Subscription.list(customer=u.stripe_customer_id,
                                        status='all', limit=20)
    except Exception:
        return 'erro consulta', False
    if not subs.data:
        return 'nunca assinou', False
    reais = [s for s in subs.data
             if s.get('status') not in ('incomplete', 'incomplete_expired')]
    if not reais:
        return 'checkout abandonado', False
    if [s for s in reais if s.get('status') in ('active', 'trialing')]:
        return 'assinatura ativa', True
    return 'cancelou', True


def ver_segmento(u, ja_pagou):
    if (u.role or '') == 'admin':
        return 'admin'
    if getattr(u, 'organization_id', None):
        return 'empresa'
    p = (u.plan_status or 'free').lower()
    if p in PAGOS:
        return 'assinante'
    if p == 'inactive':
        return 'ex-assinante'
    if p == 'past_due':
        return 'pgto pendente'
    if ja_pagou:
        return '** FREE INDEVIDO'
    pg = u.page_count or 0
    if pg >= TRIAL:
        return 'S1 esgotou'
    if pg >= 40:
        return 'S2 quase no fim'
    if pg >= 1:
        return 'S3 usou parte'
    return 'S4 nunca usou'


def ver_indicacao(u):
    linhas = db.session.execute(
        text("SELECT status, COUNT(*) c FROM referral "
             "WHERE referrer_id=:i GROUP BY status"), {'i': u.id}).fetchall()
    partes = []
    for st, c in linhas:
        partes.append(f"indicou {c}" if st == 'converted' else f"{c} {st}")
    if getattr(u, 'referred_by_code', None):
        partes.append('foi indicado')
    if u.discount_credits:
        partes.append(f'{u.discount_credits} cred')
    return ' · '.join(partes) or '-'


with app.app_context():
    usuarios = User.query.order_by(User.id).all()
    print("=" * 108)
    print(" RAIO-X DA BASE — Sistema Ponto")
    print("=" * 108)
    print(f" {'ID':<4}{'EMAIL':<32}{'PLANO':<11}{'PGS':<6}"
          f"{'SEGMENTO':<18}{'STRIPE':<20}{'INDICACAO'}")
    print("-" * 108)

    contagem, anomalias = {}, []
    for u in usuarios:
        st, ja_pagou = ver_stripe(u)
        seg = ver_segmento(u, ja_pagou)
        contagem[seg] = contagem.get(seg, 0) + 1
        if seg.startswith('**'):
            anomalias.append((u, st))
        print(f" {u.id:<4}{(u.email or '')[:31]:<32}"
              f"{(u.plan_status or ''):<11}{(u.page_count or 0):<6}"
              f"{seg:<18}{st:<20}{ver_indicacao(u)}")

    print("-" * 108)
    print(" RESUMO POR SEGMENTO")
    for seg, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"   {seg:<20} {n}")

    if anomalias:
        print("-" * 108)
        print(" ANOMALIAS — ex-assinantes com acesso free indevido")
        for u, st in anomalias:
            resta = max(0, TRIAL - (u.page_count or 0))
            print(f"   id={u.id:<4} {(u.email or '')[:34]:<35} "
                  f"{resta} paginas gratis disponiveis  ({st})")
        print(f"\n   Total: {len(anomalias)} conta(s). "
              f"Corrigir = mudar plan_status para 'inactive'.")

    ev_total = EmailEvent.query.count()
    print("-" * 108)
    print(f" E-mails registrados ate agora: {ev_total}")
    print("=" * 108)
