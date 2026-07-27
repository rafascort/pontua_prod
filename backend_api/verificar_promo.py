#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Confirma que a criacao de promotion code voltou a funcionar."""
import os
import secrets
import string
import stripe
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

from discount_service import STRIPE_API_PROMO, COUPON_WELCOME_3M

print("=" * 58)
print(f" Versao fixada : {STRIPE_API_PROMO}")
print(f" Cupom base    : {COUPON_WELCOME_3M}")
print("-" * 58)

achados = stripe.Customer.list(email='diagnostico-cupom@sistemaponto.com', limit=1)
cliente = achados.data[0] if achados.data else stripe.Customer.create(
    email='diagnostico-cupom@sistemaponto.com', description='Diagnostico')

cod = 'VERIF' + ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                        for _ in range(5))
try:
    p = stripe.PromotionCode.create(
        coupon=COUPON_WELCOME_3M, code=cod, customer=cliente.id,
        max_redemptions=1, restrictions={'first_time_transaction': True},
        stripe_version=STRIPE_API_PROMO)
    print(f" CRIADO: {p.code}  ({p.id})")
    stripe.PromotionCode.modify(p.id, active=False,
                                stripe_version=STRIPE_API_PROMO)
    print(" Desativado.")
    print("-" * 58)
    print(" CORRECAO CONFIRMADA")
except Exception as e:
    print(f" FALHOU: {e}")
print("=" * 58)
