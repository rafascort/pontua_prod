#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Projeção de 30 dias — Sistema Ponto

Simula dia a dia o que a nutrição vai enviar, usando a mesma escada e o
mesmo rodízio do lifecycle_timer.py. SOMENTE LEITURA: não envia, não
grava, não altera nada.

USO:
  python simular_30_dias.py            usa o limite atual do .env
  python simular_30_dias.py 5          simula com teto de 5/dia
  python simular_30_dias.py 5 60       teto de 5/dia, 60 dias à frente
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

import email_nurture
import email_templates
from lifecycle_timer import intervalo_para, fase_de, pool_do_usuario, TRIAL

TETO = int(sys.argv[1]) if len(sys.argv) > 1 else int(
    os.getenv('LIFECYCLE_MAX_POR_DIA', '30'))
DIAS = int(sys.argv[2]) if len(sys.argv) > 2 else 30


def _naive(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def main():
    from auth_service import app, User, EmailEvent

    hoje = datetime.now(timezone.utc).replace(tzinfo=None)

    with app.app_context():
        candidatos = User.query.filter(
            User.role != 'admin',
            User.organization_id.is_(None),
            User.email_opt_out.is_(False),
            User.email_verified.is_(True),
        ).all()

        # Estado inicial de cada pessoa
        estado = {}
        for u in candidatos:
            pool = pool_do_usuario(u)
            if not pool:
                continue
            eventos = (EmailEvent.query
                       .filter_by(user_id=u.id, email_type='nurture',
                                  status='sent')
                       .order_by(EmailEvent.sent_at.asc()).all())
            ativ = _naive(u.last_activity_at)
            n_ritmo = (sum(1 for e in eventos if _naive(e.sent_at) > ativ)
                       if ativ else len(eventos))
            usadas = 0
            for e in eventos:
                try:
                    if (json.loads(e.meta or '{}') or {}).get('pool') == pool:
                        usadas += 1
                except Exception:
                    pass
            marcos = [d for d in (ativ,
                                  _naive(eventos[-1].sent_at) if eventos else None,
                                  _naive(u.created_at)) if d]
            estado[u.id] = {
                'user': u,
                'pool': pool,
                'n_ritmo': n_ritmo,
                'usadas': usadas,
                'marco': max(marcos) if marcos else hoje - timedelta(days=999),
            }

        print("=" * 82)
        print(f" PROJEÇÃO DE {DIAS} DIAS — teto de {TETO} e-mails/dia")
        print("=" * 82)
        print(f" {len(estado)} pessoa(s) na nutrição\n")

        total = 0
        por_pessoa = {}
        calendario = []

        for dia in range(DIAS):
            data = hoje + timedelta(days=dia)
            fila = []

            for uid, st in estado.items():
                parado = (data - st['marco']).total_seconds() / 86400
                necessario = intervalo_para(
                    st['n_ritmo'], email_nurture.tamanho(st['pool']))
                if parado >= necessario:
                    fila.append((parado - necessario, uid))

            fila.sort(reverse=True)
            enviados_hoje = fila[:TETO]
            sobra = len(fila) - len(enviados_hoje)

            if not enviados_hoje:
                continue

            linhas = []
            for _, uid in enviados_hoje:
                st = estado[uid]
                u, pool = st['user'], st['pool']
                tam = email_nurture.tamanho(pool)
                var = st['usadas'] % tam
                assunto, _, _ = email_templates.render(
                    'nurture', u, {'pool': pool, 'variante': var})
                linhas.append((u.email, f"{pool}{var+1}",
                               fase_de(st['n_ritmo'], tam), assunto))
                por_pessoa[u.email] = por_pessoa.get(u.email, 0) + 1
                st['n_ritmo'] += 1
                st['usadas'] += 1
                st['marco'] = data
                total += 1

            calendario.append((dia, data, linhas, sobra))

        for dia, data, linhas, sobra in calendario:
            rotulo = "hoje" if dia == 0 else f"+{dia}d"
            print(f" DIA {dia:<3} {data:%d/%m}  ({rotulo})"
                  f"{'':4}{len(linhas)} e-mail(s)")
            print(" " + "-" * 80)
            for email, cod, fase, assunto in linhas:
                print(f"   {email[:30]:32} {cod:4} {fase:12} {assunto[:44]}")
            if sobra:
                print(f"   (+{sobra} acima do teto — vão no dia seguinte)")
            print()

        print("=" * 82)
        print(f" TOTAL: {total} e-mail(s) em {DIAS} dias\n")
        print(" Por pessoa:")
        for email, n in sorted(por_pessoa.items(), key=lambda x: -x[1]):
            print(f"   {email[:40]:42} {n} e-mail(s)")
        print("=" * 82)


if __name__ == "__main__":
    main()
