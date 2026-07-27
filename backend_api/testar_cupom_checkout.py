#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera um cupom real para uma conta sua e imprime o link de teste."""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

if len(sys.argv) < 2:
    print("Uso: python testar_cupom_checkout.py SEU_EMAIL@dominio.com")
    sys.exit(1)

from auth_service import app, User
from discount_service import create_welcome_promotion_code, is_eligible_for_welcome

FRONTEND = os.getenv('FRONTEND_URL', 'https://sistemaponto.com')

with app.app_context():
    u = User.query.filter_by(email=sys.argv[1]).first()
    if not u:
        print(f"Usuario {sys.argv[1]} nao encontrado.")
        sys.exit(1)

    ok, motivo = is_eligible_for_welcome(u)
    print("=" * 62)
    print(f" {u.email}  |  plano: {u.plan_status}  |  {u.page_count or 0} pgs")
    print(f" Elegivel: {'SIM' if ok else 'NAO'} — {motivo}")
    print("-" * 62)
    if not ok:
        print(" Use uma conta free que nunca assinou.")
        sys.exit(0)

    d = create_welcome_promotion_code(u)
    if not d:
        print(" Falha ao gerar o cupom. Veja o erro acima.")
        sys.exit(1)

    validade = datetime.fromisoformat(d['expira_em']) - timedelta(hours=3)
    print(f" Codigo    : {d['codigo']}")
    print(f" Desconto  : {d['pct_mes_1']}% no mes 1, "
          f"{d['pct_mes_2_3']}% nos meses 2 e 3")
    print(f" Valido ate: {validade:%d/%m/%Y}")
    print("-" * 62)
    print(" ABRA ESTE LINK LOGADO COM ESSA CONTA:")
    print(f"   {FRONTEND}/planos?cupom={d['codigo']}")
    print("\n Clique num plano. A pagina do Stripe deve mostrar o desconto.")
    print(" NAO precisa concluir o pagamento.")
    print("=" * 62)
