#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descobre por que PromotionCode.create falha e qual forma funciona.
Cria codigos de teste e DESATIVA todos no final."""
import os
import stripe
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

print("=" * 66)
print(" DIAGNOSTICO — PromotionCode.create")
print("=" * 66)
print(f" Biblioteca stripe : {getattr(stripe, 'VERSION', '?')}")
print(f" api_version no cod: {getattr(stripe, 'api_version', None)}")
print(f" STRIPE_API_VERSION: {os.getenv('STRIPE_API_VERSION')}")

try:
    conta = stripe.Account.retrieve()
    print(f" Conta             : {conta.get('id')}")
except Exception as e:
    print(f" [erro ao ler conta] {e}")

COUPON = 'pontua_bv10_3m'
try:
    c = stripe.Coupon.retrieve(COUPON)
    print(f" Cupom base        : {c.id} ({c.percent_off}% off, {c.duration})")
except Exception as e:
    print(f" [ERRO] Cupom {COUPON} nao encontrado: {e}")
    raise SystemExit(1)

# Cliente de teste (reaproveita se ja existir)
EMAIL_TESTE = 'diagnostico-cupom@sistemaponto.com'
achados = stripe.Customer.list(email=EMAIL_TESTE, limit=1)
cliente = achados.data[0] if achados.data else stripe.Customer.create(
    email=EMAIL_TESTE, description='Cliente temporario de diagnostico')
print(f" Cliente de teste  : {cliente.id}")

criados = []
print("\n" + "-" * 66)

# ── Tentativa 1: como esta hoje ───────────────────────────────────────
print(" [1] coupon=... (forma atual)")
try:
    p = stripe.PromotionCode.create(
        coupon=COUPON, code='DIAGTESTE01', customer=cliente.id,
        max_redemptions=1)
    criados.append(p.id)
    print(f"     OK -> {p.id}")
except Exception as e:
    print(f"     FALHOU: {e}")

# ── Tentativa 2: versao da API fixada na chamada ──────────────────────
for versao in ('2024-06-20', '2025-04-30.basil', '2023-10-16'):
    print(f" [2] coupon=... com stripe_version='{versao}'")
    try:
        p = stripe.PromotionCode.create(
            coupon=COUPON, code=f'DIAGT{versao[2:4]}{versao[5:7]}',
            customer=cliente.id, max_redemptions=1,
            stripe_version=versao)
        criados.append(p.id)
        print(f"     OK -> {p.id}   <<< FUNCIONA")
        break
    except Exception as e:
        print(f"     FALHOU: {str(e)[:120]}")

# ── Limpeza ───────────────────────────────────────────────────────────
print("-" * 66)
for pid in criados:
    try:
        stripe.PromotionCode.modify(pid, active=False)
        print(f" Desativado: {pid}")
    except Exception as e:
        print(f" [aviso] nao desativou {pid}: {e}")

print("=" * 66)
print(" Me envie esta saida inteira.")
print("=" * 66)
