#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cria os 4 cupons fixos usados pela campanha. Idempotente."""
import os
import sys
import stripe
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
if not stripe.api_key:
    print("[ERRO] STRIPE_SECRET_KEY nao encontrada no .env")
    sys.exit(1)

CUPONS = [
    {
        'id': 'pontua_bv10_3m',
        'percent_off': 10,
        'duration': 'repeating',
        'duration_in_months': 3,
        'name': 'Boas-vindas 10% (3 meses)',
        'metadata': {'source': 'welcome_campaign', 'estrutura': 'welcome_3m'},
        'uso': 'Boas-vindas sem indicacao: 10% nos meses 1, 2 e 3',
    },
    {
        'id': 'pontua_bv20_once',
        'percent_off': 20,
        'duration': 'once',
        'name': 'Boas-vindas + Indicacao 20% (1o mes)',
        'metadata': {'source': 'welcome_campaign', 'estrutura': 'welcome_ref_first'},
        'uso': 'Boas-vindas COM indicacao: 20% so no mes 1',
    },
    {
        'id': 'pontua_bv10_rest2m',
        'percent_off': 10,
        'duration': 'repeating',
        'duration_in_months': 2,
        'name': 'Boas-vindas 10% (meses 2 e 3)',
        'metadata': {'source': 'welcome_campaign', 'estrutura': 'welcome_rest_2m'},
        'uso': 'Complemento anexado apos o checkout de 20%',
    },
    {
        'id': 'pontua_ref10_once',
        'percent_off': 10,
        'duration': 'once',
        'name': 'Indicacao 10% (1 mes)',
        'metadata': {'source': 'referral_system', 'estrutura': 'referral_once'},
        'uso': 'Indicado que assina sem cupom de boas-vindas',
    },
]


def main():
    print("=" * 62)
    print(" CUPONS DA CAMPANHA — Sistema Ponto")
    print("=" * 62)
    for c in CUPONS:
        cid = c['id']
        uso = c.pop('uso')
        try:
            existente = stripe.Coupon.retrieve(cid)
            print(f"\n[JA EXISTE] {cid}")
            print(f"   {existente.percent_off}% off | duration={existente.duration}")
        except stripe.InvalidRequestError:
            try:
                novo = stripe.Coupon.create(**c)
                print(f"\n[CRIADO]    {cid}")
                print(f"   {novo.percent_off}% off | duration={novo.duration}")
            except Exception as e:
                print(f"\n[ERRO] Falha ao criar {cid}: {e}")
                sys.exit(1)
        print(f"   Uso: {uso}")

    print("\n" + "=" * 62)
    print(" Todos os cupons prontos. IDs sao fixos — nada a copiar pro .env.")
    print("=" * 62)


if __name__ == "__main__":
    main()
