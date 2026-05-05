# /opt/pontua/AutoPonto/backend_api/noturno_pareamento.py
"""
Heurística de pareamento de plantões noturnos.

ATUALIZAÇÃO: agora trata o caso especial do PRIMEIRO DIA do cartão.
Quando a primeira marcação do calendário é matinal (< 12:00),
ela é considerada saída de plantão do mês anterior (que não está
no cartão). Vai pra Sai1 sem entrada correspondente.

REGRA PRINCIPAL:
- Sistema ignora os rótulos do Document AI (entrada1, saida1, etc.)
- Olha apenas os horários crus de cada dia
- Pareia cronologicamente DENTRO do dia
- Se sobrar horário noturno (>= 12:00) isolado, pareia com matinal (< 12:00) do dia seguinte
- Aspira horários sequenciais do dia seguinte após a saída do plantão (extras)

REGRA ESPECIAL DO DIA 01:
- Se a flag noturno está ativa E é o primeiro dia do calendário E há matinal,
  esse matinal é tratado como saída órfã (sai1) e os demais horários do dia
  são processados normalmente.
"""

LIMITE_NOTURNO  = "12:00"
LIMITE_MATINAL  = "12:00"


def _coletar_horarios_do_dia(master_df, idx):
    """Coleta TODOS os horários não-zero da linha. Retorna lista de strings 'HH:MM'."""
    horarios = []
    for c in range(1, 12):
        e = master_df.at[idx, f'Entrada{c}']
        s = master_df.at[idx, f'Saida{c}']
        if e and e != "0":
            horarios.append(e)
        if s and s != "0":
            horarios.append(s)
    return horarios


def _limpar_linha(master_df, idx):
    """Zera todos os slots de Entrada/Saida da linha."""
    for c in range(1, 12):
        master_df.at[idx, f'Entrada{c}'] = "0"
        master_df.at[idx, f'Saida{c}']   = "0"


def _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=None):
    """
    Escreve os pares (entrada, saida) na linha. Limpa antes.

    Se saida_orfa_inicial está presente, ela vai pra Saida1 (sem entrada).
    Os pares depois ocupam Entrada2/Saida2, Entrada3/Saida3, etc.
    """
    _limpar_linha(master_df, idx)

    slot_inicial = 1
    if saida_orfa_inicial:
        master_df.at[idx, f'Saida1'] = saida_orfa_inicial
        slot_inicial = 2

    for i, (entrada, saida) in enumerate(pares):
        slot = slot_inicial + i
        if slot > 11:
            break
        if entrada and entrada != "0":
            master_df.at[idx, f'Entrada{slot}'] = entrada
        if saida and saida != "0":
            master_df.at[idx, f'Saida{slot}']   = saida


def _tentar_parear_dentro_do_dia(horarios_ordenados):
    """
    Pareia 2 a 2 cronologicamente. Se sobrar 1, é o "isolado".
    """
    pares = []
    sobra = list(horarios_ordenados)

    while len(sobra) >= 2:
        entrada = sobra.pop(0)
        saida   = sobra.pop(0)
        pares.append((entrada, saida))

    isolado = sobra[0] if sobra else None
    return pares, isolado


def aplicar_pareamento_noturno(master_df, log_fn=None):
    """
    Função principal — modifica master_df in-place.

    REGRA ESPECIAL: o primeiro dia do calendário, se tiver horário matinal,
    trata o PRIMEIRO matinal como saída do mês anterior (vai pra Sai1) e
    processa o restante do dia normalmente.
    """

    def _log(label, msg, level='INFO'):
        if log_fn:
            log_fn(label, msg, level)

    avisos = []
    pareados = 0
    dias_modificados = set()
    n_linhas = len(master_df)

    _log('inicio', f'Aplicando pareamento noturno em {n_linhas} dias')

    for idx in range(n_linhas):
        if idx in dias_modificados:
            continue

        horarios_dia = _coletar_horarios_do_dia(master_df, idx)
        if not horarios_dia:
            continue

        horarios_ord = sorted(horarios_dia)
        data_dia = master_df.at[idx, 'Dia']

        # ── HEURÍSTICA DO DIA 01 ─────────────────────────────────────────────
        # Se é o PRIMEIRO dia do calendário e há horário matinal,
        # o primeiro matinal é tratado como saída do mês anterior.
        saida_orfa_mes_anterior = None
        if idx == 0 and horarios_ord and horarios_ord[0] < LIMITE_MATINAL:
            saida_orfa_mes_anterior = horarios_ord[0]
            horarios_ord = horarios_ord[1:]  # remove da lista pra processar normal
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Saída ({saida_orfa_mes_anterior}) sem entrada — provavelmente plantão do mês anterior'
            })
            _log('  dia 01 especial',
                 f'{data_dia}: {saida_orfa_mes_anterior} tratado como saída do mês anterior')
        # ─────────────────────────────────────────────────────────────────────

        # Se sobrou só a saída órfã (dia 01 só tinha 1 matinal isolado), grava e segue
        if not horarios_ord:
            _escrever_pares_na_linha(master_df, idx, [], saida_orfa_inicial=saida_orfa_mes_anterior)
            continue

        pares, isolado = _tentar_parear_dentro_do_dia(horarios_ord)

        # Sem isolado: dia completo
        if isolado is None:
            _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=saida_orfa_mes_anterior)
            continue

        # Isolado matinal (< 12:00): saída órfã sem par no dia anterior
        if isolado < LIMITE_NOTURNO:
            _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=saida_orfa_mes_anterior)
            for c in range(1, 12):
                if master_df.at[idx, f'Entrada{c}'] == "0" and master_df.at[idx, f'Saida{c}'] == "0":
                    master_df.at[idx, f'Entrada{c}'] = isolado
                    break
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Marcação matinal isolada ({isolado}) — possível saída de plantão sem entrada do dia anterior, revisar manualmente'
            })
            continue

        # Isolado noturno (>= 12:00): candidato a entrada de plantão
        if idx + 1 >= n_linhas:
            _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=saida_orfa_mes_anterior)
            for c in range(1, 12):
                if master_df.at[idx, f'Entrada{c}'] == "0" and master_df.at[idx, f'Saida{c}'] == "0":
                    master_df.at[idx, f'Entrada{c}'] = isolado
                    break
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída no dia seguinte — fim do calendário'
            })
            continue

        horarios_amanha = _coletar_horarios_do_dia(master_df, idx + 1)
        if not horarios_amanha:
            data_amanha = master_df.at[idx + 1, 'Dia']
            _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=saida_orfa_mes_anterior)
            for c in range(1, 12):
                if master_df.at[idx, f'Entrada{c}'] == "0" and master_df.at[idx, f'Saida{c}'] == "0":
                    master_df.at[idx, f'Entrada{c}'] = isolado
                    break
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída — dia {data_amanha} não tem marcações'
            })
            continue

        horarios_amanha_ord = sorted(horarios_amanha)
        primeira_amanha = horarios_amanha_ord[0]

        if primeira_amanha >= LIMITE_MATINAL:
            _escrever_pares_na_linha(master_df, idx, pares, saida_orfa_inicial=saida_orfa_mes_anterior)
            for c in range(1, 12):
                if master_df.at[idx, f'Entrada{c}'] == "0" and master_df.at[idx, f'Saida{c}'] == "0":
                    master_df.at[idx, f'Entrada{c}'] = isolado
                    break
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída matinal correspondente no dia seguinte'
            })
            continue

        # ✓ Plantão pareado!
        saida_plantao = horarios_amanha_ord[0]
        extras_amanha = horarios_amanha_ord[1:]

        pares_finais = list(pares)
        pares_finais.append((isolado, saida_plantao))

        i = 0
        while i + 1 < len(extras_amanha):
            pares_finais.append((extras_amanha[i], extras_amanha[i + 1]))
            i += 2
        if i < len(extras_amanha):
            data_amanha = master_df.at[idx + 1, 'Dia']
            avisos.append({
                'data': data_amanha,
                'severidade': 'warning',
                'mensagem': f'Marcação extra ímpar ({extras_amanha[i]}) após plantão — revisar manualmente'
            })

        _escrever_pares_na_linha(master_df, idx, pares_finais, saida_orfa_inicial=saida_orfa_mes_anterior)
        _limpar_linha(master_df, idx + 1)
        dias_modificados.add(idx + 1)

        pareados += 1

        _log('  pareou', f'{data_dia}: plantão {isolado} → {saida_plantao}'
             + (f' + {len(extras_amanha)} extra(s)' if extras_amanha else ''))

    _log('total', f'{pareados} plantões pareados, {len(avisos)} aviso(s) gerado(s)')

    return {
        'avisos': avisos,
        'pareados': pareados
    }
