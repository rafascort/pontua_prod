#!/usr/bin/env python3
# /opt/pontua/AutoPonto/backend_api/patch_parse_day.py
#
# Corrige o problema onde o OCR lê um "1" adjacente junto com o número do dia,
# gerando "102" para o dia 2, "120" para o dia 20, etc.
#
# Altera SOMENTE extractor_geral_ai.py, em 3 pontos cirúrgicos:
#   1. Adiciona a função _parse_day_number (nova função auxiliar)
#   2. Corrige _entity_falls_in_period para usar _parse_day_number
#   3. Corrige a Etapa 3 (fallback_day_hits) no loop principal
#
# NÃO altera nenhuma outra lógica. Retrocompatível 100%.
#
# USO:
#   cd /opt/pontua/AutoPonto/backend_api
#   python patch_parse_day.py
#
# Backup automático criado em extractor_geral_ai.py.bak
# Para reverter: cp extractor_geral_ai.py.bak extractor_geral_ai.py

import os
import sys
import shutil

TARGET = os.path.join(os.path.dirname(__file__), 'extractor_geral_ai.py')
BACKUP = TARGET + '.bak'


def abort(msg):
    print(f'\n[ERRO] {msg}')
    print('[ERRO] Nenhuma alteração foi feita.')
    sys.exit(1)


def apply():
    # ── Lê o arquivo ──────────────────────────────────────────────────────────
    if not os.path.exists(TARGET):
        abort(f'Arquivo não encontrado: {TARGET}')

    with open(TARGET, 'r', encoding='utf-8') as f:
        src = f.read()

    # ── Idempotência: já aplicado? ────────────────────────────────────────────
    if '_parse_day_number' in src:
        print('[OK] Patch já aplicado (_parse_day_number já existe). Nada a fazer.')
        sys.exit(0)

    # ── Verifica âncoras obrigatórias ─────────────────────────────────────────
    anchors = {
        'A1': 'def _entity_falls_in_period(',
        'A2': (
            "    # Tenta extrair só o dia (número 1-31)\n"
            "    raw_clean = re.sub(r'[^\\d]', '', str(raw_data).split('/')[0])\n"
            "    if not raw_clean:\n"
            "        return None\n"
            "\n"
            "    try:\n"
            "        dia_num = int(raw_clean)\n"
            "    except ValueError:\n"
            "        return None\n"
            "\n"
            "    if not (1 <= dia_num <= 31):\n"
            "        return None\n"
        ),
        'A3': (
            "                if target_date is None and raw_dia:\n"
            "                    raw_clean = re.sub(r'[^\\d]', '', str(raw_dia).split('/')[0])\n"
            "                    if raw_clean:\n"
            "                        try:\n"
            "                            n = int(raw_clean)\n"
            "                            if 1 <= n <= 31:\n"
            "                                day_str   = f\"{n:02d}\"\n"
            "                                # Procura primeira data do período da página com esse dia\n"
            "                                day_match = next(\n"
            "                                    (d for d in page_dates if d.startswith(day_str + '/')),\n"
            "                                    None\n"
            "                                )\n"
            "                                if day_match and day_match in date_to_row:\n"
            "                                    target_date = day_match\n"
            "                                    fallback_day_hits += 1\n"
            "                                    new_ptr = page_dates.index(day_match)\n"
            "                                    if new_ptr >= page_row_ptr:\n"
            "                                        page_row_ptr = new_ptr + 1\n"
            "                        except (ValueError, OverflowError):\n"
            "                            pass\n"
        ),
    }

    missing = [k for k, v in anchors.items() if v not in src]
    if missing:
        abort(
            'As seguintes âncoras não foram encontradas no arquivo '
            '(versão diferente do esperado):\n  ' + ', '.join(missing)
        )

    print('[INFO] Todas as âncoras encontradas.')

    # ── Backup ────────────────────────────────────────────────────────────────
    shutil.copy2(TARGET, BACKUP)
    print(f'[INFO] Backup criado: {BACKUP}')

    out = src

    # =========================================================================
    # PATCH 1 — Inserir _parse_day_number logo antes de _entity_falls_in_period
    # =========================================================================
    #
    # POR QUÊ É SEGURO:
    #   É uma função nova, puramente aditiva. Não altera nada existente.
    #   Retorna int(1-31) ou None. Nunca lança exceção.
    #
    # LÓGICA DA CORREÇÃO:
    #   O OCR lê um caractere "1" adjacente junto com o dia:
    #     "1" + "02" → "102"  (esperado: dia 2)
    #     "1" + "20" → "120"  (esperado: dia 20)
    #   Se o número for > 31, tenta os últimos 2 dígitos.
    #   Isso é seguro porque códigos de jornada (684, 795, 796...)
    #   têm últimos 2 dígitos > 31 e continuam sendo corretamente rejeitados:
    #     "684" → últimos 2 = "84" → 84 > 31 → None ✓
    #     "795" → últimos 2 = "95" → 95 > 31 → None ✓
    #     "102" → últimos 2 = "02" → 2  ≤ 31 → 2   ✓
    #     "120" → últimos 2 = "20" → 20 ≤ 31 → 20  ✓

    NEW_FUNC = '''\
def _parse_day_number(raw_str):
    """
    Extrai número do dia (1-31) de uma string bruta do DocAI,
    tolerando o artefato OCR onde um "1" adjacente é lido junto
    com o número do dia (ex: "102" para dia 2, "120" para dia 20).

    Regra de correção (segura):
      Se o número extraído > 31, tenta os últimos 2 dígitos.
      Códigos de jornada (684, 795, 796…) têm últimos 2 dígitos
      acima de 31 e continuam sendo rejeitados corretamente.

    Retorna int entre 1 e 31, ou None se não for possível extrair
    um dia válido. Nunca lança exceção.
    """
    if not raw_str:
        return None
    raw_clean = re.sub(r'[^\\d]', '', str(raw_str).split('/')[0])
    if not raw_clean:
        return None
    try:
        n = int(raw_clean)
    except (ValueError, OverflowError):
        return None

    # Caso normal: já é um dia válido
    if 1 <= n <= 31:
        return n

    # Artefato OCR: "1" prefixado — tenta últimos 2 dígitos
    # Exemplo: "102" → 02 = 2 ✓  |  "120" → 20 ✓  |  "684" → 84 > 31 ✗
    if n > 31 and len(raw_clean) >= 3:
        tail = int(raw_clean[-2:])
        if 1 <= tail <= 31:
            return tail

    return None


'''

    idx = out.find('def _entity_falls_in_period(')
    if idx == -1:
        abort('Posição de inserção (def _entity_falls_in_period) não encontrada.')
    out = out[:idx] + NEW_FUNC + out[idx:]
    print('[OK] Patch 1: _parse_day_number inserida.')

    # =========================================================================
    # PATCH 2 — Substituir parse manual do dia em _entity_falls_in_period
    # =========================================================================
    #
    # POR QUÊ É SEGURO:
    #   Substitui exatamente as 10 linhas de parse manual por 1 chamada ao
    #   helper. O comportamento é idêntico para todos os inputs válidos.
    #   A única diferença: "102" agora resolve para dia 2 em vez de ser
    #   descartado — que é exatamente o bug que estamos corrigindo.
    #   Nenhuma outra lógica da função muda.

    OLD_2 = (
        "    # Tenta extrair só o dia (número 1-31)\n"
        "    raw_clean = re.sub(r'[^\\d]', '', str(raw_data).split('/')[0])\n"
        "    if not raw_clean:\n"
        "        return None\n"
        "\n"
        "    try:\n"
        "        dia_num = int(raw_clean)\n"
        "    except ValueError:\n"
        "        return None\n"
        "\n"
        "    if not (1 <= dia_num <= 31):\n"
        "        return None\n"
    )
    NEW_2 = (
        "    # Extrai o número do dia usando helper que trata artefato OCR '1XX'\n"
        "    # Ex: '102' → 2, '120' → 20; códigos de jornada (684, 795) → None\n"
        "    dia_num = _parse_day_number(raw_data)\n"
        "    if dia_num is None:\n"
        "        return None\n"
    )

    if OLD_2 not in out:
        abort('Âncora A2 (_entity_falls_in_period body) sumiu após patch 1.')
    out = out.replace(OLD_2, NEW_2, 1)
    print('[OK] Patch 2: _entity_falls_in_period atualizada.')

    # =========================================================================
    # PATCH 3 — Substituir Etapa 3 (fallback_day_hits) no loop principal
    # =========================================================================
    #
    # POR QUÊ É SEGURO:
    #   O bloco antigo tinha try/except (ValueError, OverflowError) e um
    #   if 1 <= n <= 31. O novo helper encapsula exatamente essa mesma lógica
    #   mais o tratamento do artefato "1XX". O resultado para todos os inputs
    #   que antes funcionavam é idêntico. Para "102", "120" etc., agora
    #   resolve corretamente em vez de cair no fallback Y (que era a causa
    #   dos horários errados nos dias afetados).

    OLD_3 = (
        "                if target_date is None and raw_dia:\n"
        "                    raw_clean = re.sub(r'[^\\d]', '', str(raw_dia).split('/')[0])\n"
        "                    if raw_clean:\n"
        "                        try:\n"
        "                            n = int(raw_clean)\n"
        "                            if 1 <= n <= 31:\n"
        "                                day_str   = f\"{n:02d}\"\n"
        "                                # Procura primeira data do período da página com esse dia\n"
        "                                day_match = next(\n"
        "                                    (d for d in page_dates if d.startswith(day_str + '/')),\n"
        "                                    None\n"
        "                                )\n"
        "                                if day_match and day_match in date_to_row:\n"
        "                                    target_date = day_match\n"
        "                                    fallback_day_hits += 1\n"
        "                                    new_ptr = page_dates.index(day_match)\n"
        "                                    if new_ptr >= page_row_ptr:\n"
        "                                        page_row_ptr = new_ptr + 1\n"
        "                        except (ValueError, OverflowError):\n"
        "                            pass\n"
    )
    NEW_3 = (
        "                # Etapa 3: nº do dia pelo DocAI — helper trata artefato OCR '1XX'\n"
        "                if target_date is None and raw_dia:\n"
        "                    n = _parse_day_number(raw_dia)\n"
        "                    if n is not None:\n"
        "                        day_str   = f\"{n:02d}\"\n"
        "                        # Procura primeira data do período da página com esse dia\n"
        "                        day_match = next(\n"
        "                            (d for d in page_dates if d.startswith(day_str + '/')),\n"
        "                            None\n"
        "                        )\n"
        "                        if day_match and day_match in date_to_row:\n"
        "                            target_date = day_match\n"
        "                            fallback_day_hits += 1\n"
        "                            new_ptr = page_dates.index(day_match)\n"
        "                            if new_ptr >= page_row_ptr:\n"
        "                                page_row_ptr = new_ptr + 1\n"
    )

    if OLD_3 not in out:
        abort('Âncora A3 (Etapa 3 fallback_day_hits) não encontrada.')
    out = out.replace(OLD_3, NEW_3, 1)
    print('[OK] Patch 3: Etapa 3 (fallback_day_hits) atualizada.')

    # ── Grava resultado ───────────────────────────────────────────────────────
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(out)

    print()
    print('=' * 60)
    print('[SUCESSO] 3 alterações aplicadas.')
    print(f'[INFO]    Backup disponível em: {BACKUP}')
    print('=' * 60)
    print()
    print('Verificação rápida:')
    print('  python -c "import extractor_geral_ai; print(\'OK\')"')
    print()
    print('Restart do worker:')
    print('  sudo systemctl restart rq_global_worker.service')


if __name__ == '__main__':
    apply()
