#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_dia_multimes.py
=====================================================================
CORREÇÃO: colisão de nº do dia em páginas que cobrem MAIS DE UM MÊS.

PROBLEMA
--------
Na Etapa 3 da resolução de datas (extractor_geral_ai.py), o nº do dia
(1-31) extraído pelo DocAI era casado com a PRIMEIRA data do período da
página que tivesse aquele dia-do-mês:

    day_match = next(
        (d for d in page_dates if d.startswith(day_str + '/')),  # <- do INÍCIO
        None
    )

Quando uma única página cobre 2+ meses (ex.: 20/12 -> 05/02), o número
"24" existe em 24/dez E 24/jan. As duas linhas eram roteadas para 24/dez:
a 1ª preenchia, a 2ª caía em "continuação mesclada" / "duplicado ignorado",
e 24/jan ficava VAZIO.

CORREÇÃO
--------
As entidades chegam em ordem cronológica (spatial_sort por Y). Então o nº
do dia é casado com a próxima data A PARTIR do cursor cronológico
(page_row_ptr), e não do início da página:

    (a) continuação do mesmo dia (linha extra de marcações) -> fica no dia
        já preenchido (não empurra p/ o mês seguinte);
    (b) caso normal -> próxima data com esse dia a partir do cursor;
    (c) último recurso (entidade fora de ordem) -> busca do início (igual
        ao comportamento antigo, preservado por segurança).

POR QUE É SEGURO PARA OUTROS FORMATOS
-------------------------------------
- Página de um único mês: o dia é único em page_dates -> (b) acha a mesma
  data de sempre. Comportamento idêntico ao atual.
- Linha de continuação (mesmo dia repetido): (a) mantém na mesma data,
  preservando a mescla que já existia.
- Página multi-mês: corrige o roteamento (era a origem das duplicatas).

Idempotente: se já estiver corrigido, não faz nada.
Faz backup .bak com timestamp, valida com py_compile e reverte em caso de erro.
=====================================================================
"""

import os
import re
import sys
import shutil
import py_compile
from datetime import datetime

TARGET = "/opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py"


def abort(msg):
    print(f"[ERRO] {msg}")
    sys.exit(1)


# ── Bloco atual (âncora exata) ──────────────────────────────────────────────
OLD = (
'                        day_str   = f"{n:02d}"\n'
'                        # Procura primeira data do período da página com esse dia\n'
'                        day_match = next(\n'
"                            (d for d in page_dates if d.startswith(day_str + '/')),\n"
'                            None\n'
'                        )\n'
'                        if day_match and day_match in date_to_row:\n'
)

# ── Bloco corrigido ─────────────────────────────────────────────────────────
NEW = (
'                        day_str   = f"{n:02d}"\n'
'                        # CORREÇÃO multi-mês: o nº do dia (1-31) repete quando a\n'
'                        # página cobre mais de um mês (ex.: "24" = 24/dez E 24/jan).\n'
'                        # As entidades chegam em ordem cronológica (spatial_sort por Y),\n'
'                        # então casamos o dia A PARTIR do cursor (page_row_ptr), e não\n'
'                        # do início da página — assim 24/dez -> 1º "24" e 24/jan -> 2º.\n'
'                        day_match = None\n'
'                        # (a) continuação do mesmo dia (linha extra de marcações):\n'
'                        #     nº do dia == dia da última data preenchida -> fica nela.\n'
'                        if page_row_ptr > 0 and page_dates[page_row_ptr - 1].startswith(day_str + \'/\'):\n'
'                            day_match = page_dates[page_row_ptr - 1]\n'
'                        # (b) caso normal: próxima data com esse dia a partir do cursor.\n'
'                        if day_match is None:\n'
'                            day_match = next(\n'
"                                (d for d in page_dates[page_row_ptr:] if d.startswith(day_str + '/')),\n"
'                                None\n'
'                            )\n'
'                        # (c) último recurso (entidade fora de ordem): busca do início.\n'
'                        if day_match is None:\n'
'                            day_match = next(\n'
"                                (d for d in page_dates if d.startswith(day_str + '/')),\n"
'                                None\n'
'                            )\n'
'                        if day_match and day_match in date_to_row:\n'
)


def main():
    if not os.path.isfile(TARGET):
        abort(f"Arquivo alvo não encontrado: {TARGET}")

    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    # ── Idempotência ────────────────────────────────────────────────────────
    if "page_dates[page_row_ptr:]" in src:
        print("[INFO] Correção já aplicada (encontrado 'page_dates[page_row_ptr:]').")
        print("[INFO] Nada a fazer. Saindo.")
        return

    # ── Âncora ──────────────────────────────────────────────────────────────
    ocorrencias = src.count(OLD)
    if ocorrencias == 0:
        abort("Âncora da Etapa 3 não encontrada. O arquivo pode já ter "
              "sido editado manualmente. Patch abortado (nada alterado).")
    if ocorrencias > 1:
        abort(f"Âncora encontrada {ocorrencias}x (esperado 1). "
              "Patch abortado por segurança.")

    # ── Backup ──────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{TARGET}.bak_{ts}"
    shutil.copy2(TARGET, backup)
    print(f"[OK ] Backup criado: {backup}")

    # ── Substituição ────────────────────────────────────────────────────────
    out = src.replace(OLD, NEW, 1)
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(out)
    print("[OK ] Bloco da Etapa 3 substituído.")

    # ── Sanity check: py_compile (auto-revert em caso de erro) ──────────────
    try:
        py_compile.compile(TARGET, doraise=True)
        print("[OK ] py_compile passou — sintaxe válida.")
    except py_compile.PyCompileError as e:
        print(f"[ERRO] py_compile falhou:\n{e}")
        shutil.copy2(backup, TARGET)
        print(f"[OK ] Revertido a partir do backup: {backup}")
        sys.exit(1)

    print("\n========================================================")
    print("PATCH APLICADO COM SUCESSO.")
    print("========================================================")
    print("Verificação rápida (deve mostrar as 3 novas etapas a/b/c):")
    print(f"  grep -n 'page_dates\\[page_row_ptr:\\]' {TARGET}")
    print(f"  grep -n 'CORREÇÃO multi-mês' {TARGET}")
    print("\nReinício do serviço (rode você quando quiser — NÃO foi reiniciado):")
    print("  sudo systemctl restart queue_manager.service rq_global_worker.service")
    print("\nRollback, se precisar:")
    print(f"  sudo cp {backup} {TARGET}")
    print(f"  sudo systemctl restart queue_manager.service rq_global_worker.service")


if __name__ == "__main__":
    main()
