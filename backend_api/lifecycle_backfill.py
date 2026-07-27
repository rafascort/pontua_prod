#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entrada da base antiga — Sistema Ponto

Envio ÚNICO para quem já estava cadastrado antes da campanha. Cada
segmento recebe um e-mail diferente, pelo estado real da conta.

  S1  esgotou o trial (>=50)      -> trial_end_coupon (gera cupom)
  S2  quase no fim (40-49)        -> trial_80
  S3  usou parte (1-39)           -> reactivate_partial
  S4  nunca usou (0)              -> reactivate_never
  EX  ex-assinante (inactive)     -> winback_ex

USO:
  python lifecycle_backfill.py                    # simula tudo
  python lifecycle_backfill.py --grupo S1         # simula um grupo
  python lifecycle_backfill.py --grupo S1 --aplicar   # ENVIA

Independe do LIFECYCLE_EMAILS_ENABLED: é uma ação manual e deliberada.
Reexecutar é seguro — o email_event impede envio duplicado.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

import lifecycle_email_service as mailer

TRIAL = 50
PAUSA = 2.0
FRONTEND = os.getenv('FRONTEND_URL', 'https://sistemaponto.com')

GRUPOS = {
    'S1': ('Esgotou o trial',      'trial_end_coupon'),
    'S2': ('Quase no fim (40-49)', 'trial_80'),
    'S3': ('Usou parte (1-39)',    'reactivate_partial'),
    'S4': ('Nunca usou',           'reactivate_never'),
    'EX': ('Ex-assinante',         'winback_ex'),
}

APLICAR = '--aplicar' in sys.argv
FILTRO = None
if '--grupo' in sys.argv:
    i = sys.argv.index('--grupo')
    if i + 1 < len(sys.argv):
        FILTRO = sys.argv[i + 1].upper()


def classificar(u):
    plano = (u.plan_status or 'free').lower()
    if plano == 'inactive':
        return 'EX'
    if plano != 'free':
        return None
    pg = u.page_count or 0
    if pg >= TRIAL:
        return 'S1'
    if pg >= 40:
        return 'S2'
    if pg >= 1:
        return 'S3'
    return 'S4'


def contexto_cupom(u):
    """Gera o cupom pessoal. Devolve (tipo, contexto)."""
    try:
        from discount_service import create_welcome_promotion_code
        d = create_welcome_promotion_code(u)
        if not d:
            print(f"    [!] {u.email}: não passou no portão do cupom; "
                  f"enviando versão sem desconto.")
            return 'trial_end_plain', {}
        validade = datetime.fromisoformat(d['expira_em']) - timedelta(hours=3)
        return 'trial_end_coupon', {
            'codigo': d['codigo'],
            'validade': validade.strftime('%d/%m/%Y'),
            'pct_mes_1': d['pct_mes_1'],
            'pct_mes_2_3': d['pct_mes_2_3'],
            'link': f"{FRONTEND}/planos?cupom={d['codigo']}",
            'expira_em_ts': d['expira_em_ts'],
        }
    except Exception as e:
        print(f"    [!] {u.email}: erro ao gerar cupom ({e}); "
              f"enviando versão sem desconto.")
        return 'trial_end_plain', {}


def main():
    from auth_service import app, User

    print("=" * 76)
    print(" ENTRADA DA BASE ANTIGA — Sistema Ponto")
    print("=" * 76)
    print(f" Modo  : {'ENVIO REAL' if APLICAR else 'SIMULAÇÃO'}")
    print(f" Grupo : {FILTRO or 'todos'}")

    if FILTRO and FILTRO not in GRUPOS:
        print(f"\n [ERRO] Grupo '{FILTRO}' não existe. "
              f"Use: {', '.join(GRUPOS)}")
        sys.exit(1)

    with app.app_context():
        usuarios = User.query.filter(
            User.role != 'admin',
            User.organization_id.is_(None),
            User.email_opt_out.is_(False),
        ).order_by(User.id).all()

        buckets = {g: [] for g in GRUPOS}
        pulados = []
        for u in usuarios:
            g = classificar(u)
            if not g:
                continue
            if not u.email_verified:
                pulados.append((u, 'e-mail nunca verificado'))
                continue
            tipo = GRUPOS[g][1]
            if mailer.already_sent(u.id, tipo) or \
               (g == 'S1' and mailer.already_sent(u.id, 'trial_end_plain')):
                pulados.append((u, f'já recebeu {tipo}'))
                continue
            buckets[g].append(u)

        total = 0
        for g, (nome, tipo) in GRUPOS.items():
            lista = buckets[g]
            if FILTRO and g != FILTRO:
                continue
            if not lista:
                continue
            total += len(lista)
            print(f"\n {g} · {nome} -> {tipo}   ({len(lista)} pessoa(s))")
            print(" " + "-" * 74)
            for u in lista:
                nome_u = (u.first_name or '').strip() or '—'
                print(f"   {u.email[:38]:40} {u.page_count or 0:>3}pg   {nome_u}")

        if pulados:
            print(f"\n Ignorados ({len(pulados)}):")
            for u, motivo in pulados:
                print(f"   {u.email[:38]:40} {motivo}")

        print("\n" + "-" * 76)
        if total == 0:
            print(" Nada a enviar.")
            print("=" * 76)
            return

        if not APLICAR:
            print(f" SIMULAÇÃO — {total} e-mail(s) seriam enviados. Nada saiu.")
            print("\n Para enviar de verdade, um grupo por vez:")
            for g in (FILTRO,) if FILTRO else GRUPOS:
                if buckets.get(g):
                    print(f"   python lifecycle_backfill.py --grupo {g} --aplicar")
            print("=" * 76)
            return

        print(f" ENVIANDO {total} e-mail(s)...\n")
        ok = falhas = 0
        for g, (nome, tipo_padrao) in GRUPOS.items():
            if FILTRO and g != FILTRO:
                continue
            for u in buckets[g]:
                if g == 'S1':
                    tipo, ctx = contexto_cupom(u)
                else:
                    tipo, ctx = tipo_padrao, {}
                if mailer.send(u, tipo, ctx):
                    ok += 1
                else:
                    falhas += 1
                time.sleep(PAUSA)

        print("-" * 76)
        print(f" Enviados: {ok}  |  Falhas: {falhas}")
        print("=" * 76)


if __name__ == "__main__":
    main()
