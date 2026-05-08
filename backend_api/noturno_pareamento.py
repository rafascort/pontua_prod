# /opt/pontua/AutoPonto/backend_api/noturno_pareamento.py
"""
Heurística de pareamento de plantões noturnos.

REGRAS:

1. Sistema ignora os rótulos do Document AI (entrada1, saida1, etc.)
   Olha apenas os horários crus de cada dia.

2. HEURÍSTICA DO DIA 01: se é o primeiro dia do calendário e a primeira
   marcação é matinal (< 12:00), trata como saída do mês anterior (vai pra Sai1).

3. PAREAMENTO DENTRO DO DIA: pareia 2 a 2 cronologicamente os horários do dia.

4. NOTURNO ISOLADO: quando sobra um horário noturno (>= 12:00) sem par no
   próprio dia, é candidato a entrada de plantão. Procura matinal no dia D+1.

5. ASPIRAÇÃO INTELIGENTE: quando o plantão é pareado, aspira do dia D+1:
   - A saída do plantão (primeira marcação matinal)
   - Pares cronológicos consecutivos depois dela (extras pós-plantão)
   - Para de aspirar quando sobrar horário ímpar (que fica no D+1 como
     possível novo plantão noturno)

6. MATINAL ISOLADO: se um dia D tem matinal sobrando sem ter sido aspirado
   pelo dia anterior, é saída órfã sem entrada do dia anterior.
   Vai pra Sai1 (não Ent1) com aviso.

7. ESCRITA CRONOLÓGICA: ao escrever os horários no master_df, mantém a
   ordem cronológica natural (extras antes do plantão vão antes; extras
   depois do plantão vão depois).
"""

LIMITE_NOTURNO  = "12:00"   # >= 12:00 = noturno (entrada de plantão)
LIMITE_MATINAL  = "12:00"   # <  12:00 = matinal (saída de plantão)


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


def _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, entrada_orfa_final=None):
    """
    Escreve o resultado do processamento de um dia no master_df.

    Argumentos:
        saida_orfa_inicial: horário matinal isolado (vai pra Saida1, sem Entrada1)
        pares: lista de tuplas (entrada, saida) cronológicas
        entrada_orfa_final: horário noturno sem saída encontrada (vai pra próxima Entrada vazia)

    Limpa a linha antes de escrever.
    """
    _limpar_linha(master_df, idx)

    slot_inicial = 1
    if saida_orfa_inicial and saida_orfa_inicial != "0":
        master_df.at[idx, 'Saida1'] = saida_orfa_inicial
        slot_inicial = 2

    for i, (entrada, saida) in enumerate(pares):
        slot = slot_inicial + i
        if slot > 11:
            break  # CSV tem só 11 slots
        if entrada and entrada != "0":
            master_df.at[idx, f'Entrada{slot}'] = entrada
        if saida and saida != "0":
            master_df.at[idx, f'Saida{slot}']   = saida

    if entrada_orfa_final and entrada_orfa_final != "0":
        for c in range(1, 12):
            if master_df.at[idx, f'Entrada{c}'] == "0" and master_df.at[idx, f'Saida{c}'] == "0":
                master_df.at[idx, f'Entrada{c}'] = entrada_orfa_final
                break


def _parear_dois_a_dois(horarios_ordenados):
    """
    Pareia 2 a 2 cronologicamente. Se sobrar 1, retorna em sobra.
    Retorna: (lista de pares, sobra_único_ou_None)
    """
    pares = []
    sobra = list(horarios_ordenados)

    while len(sobra) >= 2:
        entrada = sobra.pop(0)
        saida   = sobra.pop(0)
        pares.append((entrada, saida))

    isolado = sobra[0] if sobra else None
    return pares, isolado


def _aspirar_inteligente_do_amanha(horarios_amanha_ord):
    """
    NOVA REGRA: aspira do dia seguinte pra incluir no expediente do dia atual.

    Aspira:
    - A primeira marcação (saída do plantão)
    - Pares cronológicos consecutivos depois dela (extras pós-plantão)
    - Para quando sobra horário ímpar (que fica no D+1)

    Exemplos:
        [07:05]                       → aspira [07:05], sobra []
        [07:05, 13:14, 18:18]         → aspira [07:05, 13:14, 18:18], sobra []
        [07:05, 18:00]                → aspira [07:05], sobra [18:00] (ímpar resta)
        [07:05, 13:14, 18:18, 22:00]  → aspira [07:05, 13:14, 18:18], sobra [22:00]
        [07:05, 13:14, 18:18, 22:00, 23:30] → aspira [07:05, 13:14, 18:18, 22:00, 23:30], sobra []

    Retorna: (lista_aspirada, lista_que_sobra_no_amanha)
    """
    if not horarios_amanha_ord:
        return [], []

    # Aspira a saída do plantão (1º horário) + pares 2 a 2 enquanto possível
    saida_plantao = horarios_amanha_ord[0]
    aspirados = [saida_plantao]
    resto = horarios_amanha_ord[1:]

    # Pareia o resto 2 a 2 — só inclui na aspiração se formar par completo
    while len(resto) >= 2:
        aspirados.append(resto[0])
        aspirados.append(resto[1])
        resto = resto[2:]

    # Se sobrou 1 ímpar, ele NÃO é aspirado (fica no D+1)
    return aspirados, resto


def aplicar_pareamento_noturno(master_df, log_fn=None):
    """
    Função principal — modifica master_df in-place.
    Retorna dict com 'avisos' (list) e 'pareados' (int).
    """

    def _log(label, msg, level='INFO'):
        if log_fn:
            log_fn(label, msg, level)

    avisos = []
    pareados = 0
    matinais_aspirados = set()  # idx dos dias cuja primeira marcação foi aspirada
    dias_totalmente_aspirados = set()  # idx dos dias TODOS aspirados (ficam vazios)
    n_linhas = len(master_df)

    _log('inicio', f'Aplicando pareamento noturno em {n_linhas} dias')

    for idx in range(n_linhas):
        # Se este dia foi totalmente aspirado pelo dia anterior, pula
        if idx in dias_totalmente_aspirados:
            continue

        horarios_dia = _coletar_horarios_do_dia(master_df, idx)
        if not horarios_dia:
            continue

        horarios_ord = sorted(horarios_dia)
        data_dia = master_df.at[idx, 'Dia']

        # Se este dia teve hor[arios aspirados parcialmente, remove os já consumidos
        if idx in matinais_aspirados and idx not in dias_totalmente_aspirados:
            # As primeiras N marcações foram consumidas — sobra é o que está em master_df
            # Como _coletar lê do master_df e ele já foi limpo dos aspirados, está ok
            pass

        # ── HEURÍSTICA DO DIA 01: matinal no primeiro dia = saída do mês anterior
        saida_orfa_inicial = None
        if idx == 0 and horarios_ord and horarios_ord[0] < LIMITE_MATINAL:
            saida_orfa_inicial = horarios_ord[0]
            horarios_ord = horarios_ord[1:]
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Saída ({saida_orfa_inicial}) sem entrada — provavelmente plantão do mês anterior'
            })
            _log('  dia 01 especial',
                 f'{data_dia}: {saida_orfa_inicial} tratado como saída do mês anterior')

        # ── MATINAL ISOLADO em dia que não foi aspirado pelo anterior
        if (saida_orfa_inicial is None and idx > 0 and idx not in matinais_aspirados
                and horarios_ord and horarios_ord[0] < LIMITE_MATINAL):
            saida_orfa_inicial = horarios_ord[0]
            horarios_ord = horarios_ord[1:]
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Marcação matinal isolada ({saida_orfa_inicial}) — possível saída de plantão sem entrada do dia anterior, revisar manualmente'
            })

        # Se sobrou só a saída órfã, grava e segue
        if not horarios_ord:
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, [], None)
            continue

        # ── PAREAMENTO 2 A 2 cronológico
        pares, isolado = _parear_dois_a_dois(horarios_ord)

        # Sem isolado: dia completo
        if isolado is None:
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, None)
            continue

        # Isolado matinal (caso raro): adiciona como saída extra
        if isolado < LIMITE_NOTURNO:
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, None)
            for c in range(1, 12):
                if master_df.at[idx, f'Saida{c}'] == "0":
                    master_df.at[idx, f'Saida{c}'] = isolado
                    break
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Marcação matinal extra ({isolado}) — verificar contexto, possível saída sem entrada correspondente'
            })
            continue

        # ── ISOLADO NOTURNO: candidato a entrada de plantão
        # Procura matinal no dia seguinte
        if idx + 1 >= n_linhas:
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, isolado)
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída no dia seguinte — fim do calendário'
            })
            continue

        horarios_amanha = _coletar_horarios_do_dia(master_df, idx + 1)
        if not horarios_amanha:
            data_amanha = master_df.at[idx + 1, 'Dia']
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, isolado)
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída — dia {data_amanha} não tem marcações'
            })
            continue

        horarios_amanha_ord = sorted(horarios_amanha)
        primeira_amanha = horarios_amanha_ord[0]

        if primeira_amanha >= LIMITE_MATINAL:
            _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares, isolado)
            avisos.append({
                'data': data_dia,
                'severidade': 'warning',
                'mensagem': f'Entrada noturna ({isolado}) sem saída matinal correspondente no dia seguinte'
            })
            continue

        # ✓ PLANTÃO PAREADO!
        # NOVA: aspiração inteligente
        aspirados_amanha, resto_amanha = _aspirar_inteligente_do_amanha(horarios_amanha_ord)
        saida_plantao = aspirados_amanha[0]
        extras_pos_plantao = aspirados_amanha[1:]  # tudo após a saída do plantão

        # Atualiza dia D+1: limpa e regrava só o que sobrou
        if not resto_amanha:
            # D+1 fica totalmente vazio
            _limpar_linha(master_df, idx + 1)
            dias_totalmente_aspirados.add(idx + 1)
        else:
            # D+1 fica com o que sobrou (será reprocessado quando chegar a vez)
            _limpar_linha(master_df, idx + 1)
            for i, h in enumerate(resto_amanha):
                # Coloca em Entrada1, Entrada2, etc. — vai ser reprocessado
                # Como é um único horário restante, vira Entrada1 (que depois pode virar plantão)
                master_df.at[idx + 1, f'Entrada{i+1}'] = h
            matinais_aspirados.add(idx + 1)

        # Constrói pares finais cronologicamente
        # Combina: pares pré-plantão (do dia D) + plantão + extras pós-plantão (do dia D+1)
        pares_finais = list(pares)  # pares formados dentro do dia D antes do plantão
        pares_finais.append((isolado, saida_plantao))  # o plantão

        # Pareia os extras pós-plantão 2 a 2
        i = 0
        while i + 1 < len(extras_pos_plantao):
            pares_finais.append((extras_pos_plantao[i], extras_pos_plantao[i + 1]))
            i += 2

        # Re-ordena pares cronologicamente pelo horário de entrada
        # (importante quando há extras antes do plantão no dia D)
        pares_finais.sort(key=lambda p: p[0])

        _escrever_resultado_do_dia(master_df, idx, saida_orfa_inicial, pares_finais, None)
        pareados += 1

        extras_count = len(extras_pos_plantao) // 2
        _log('  pareou', f'{data_dia}: plantão {isolado} → {saida_plantao}'
             + (f' + {len(pares)} HE pré' if pares else '')
             + (f' + {extras_count} HE pós' if extras_count else '')
             + (f' (dia seguinte mantém {len(resto_amanha)} marcação)' if resto_amanha else ''))

    _log('total', f'{pareados} plantões pareados, {len(avisos)} aviso(s) gerado(s)')

    return {
        'avisos': avisos,
        'pareados': pareados
    }
