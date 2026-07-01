# /opt/pontua/AutoPonto/backend_api/avisos_ponto.py
"""
Avisos de validacao do Extrator de Ponto — Sistema Ponto

Centraliza a geracao de avisos pos-extracao exibidos no WarningsModal.

Formato de cada aviso (compativel com AvisoItem no frontend):
    {
        'data':       'dd/mm/yyyy',
        'severidade': 'info' | 'warning' | 'danger',
        'mensagem':   'texto exibido ao perito',
        'tipo':       'codigo_maquina'   # opcional — para agrupar/filtrar
    }

COMO ADICIONAR UM NOVO TIPO DE AVISO:
    1. Escreva validar_xxx(master_df, datas_ignorar=None) -> list[aviso]
       (use o helper novo_aviso()).
    2. Registre a funcao na lista VALIDADORES, no fim do arquivo.
    coletar_avisos() passa a executa-la automaticamente.

master_df:
    - coluna 'Dia' -> 'dd/mm/yyyy'
    - colunas de marcacao 'Entrada1','Saida1','Entrada2',... (vazio = "0")
"""
from __future__ import annotations

import re
from datetime import datetime


# =====================================================================
# HELPERS DE ESTRUTURA
# =====================================================================

_RE_MARCACAO = re.compile(r'^(Entrada|Saida)\d+$')


def novo_aviso(data, severidade, mensagem, tipo=None):
    """Monta um aviso no formato esperado pelo frontend."""
    aviso = {'data': data, 'severidade': severidade, 'mensagem': mensagem}
    if tipo:
        aviso['tipo'] = tipo
    return aviso


def _colunas_marcacao(master_df):
    """Detecta dinamicamente todas as colunas Entrada{n}/Saida{n}."""
    return [c for c in master_df.columns if _RE_MARCACAO.match(str(c))]


def _valor_preenchido(valor):
    """True se a celula contem uma marcacao real (nao vazia / nao '0')."""
    s = str(valor).strip()
    return s not in ("", "0", "nan", "NaN", "None")


def _contar_marcacoes(master_df, idx, cols):
    return sum(1 for c in cols if _valor_preenchido(master_df.at[idx, c]))


def ordenar_avisos(avisos):
    """Ordena cronologicamente por 'data' (dd/mm/yyyy); invalidos vao ao fim."""
    def _chave(a):
        try:
            return datetime.strptime(a.get('data', ''), '%d/%m/%Y')
        except (ValueError, TypeError):
            return datetime.max
    return sorted(avisos, key=_chave)


# =====================================================================
# VALIDADORES (cada um retorna uma lista de avisos)
# =====================================================================

def validar_jornada_impar(master_df, datas_ignorar=None, **kwargs):
    """
    Sinaliza dias com numero IMPAR de marcacoes (entrada/saida desemparelhadas).
    Ex.: Entrada1 + Saida1 + Entrada2 (sem Saida2) -> 3 marcacoes -> incompleta.
    Dias sem marcacao (folga/feriado) sao ignorados (0 e par).
    """
    datas_ignorar = datas_ignorar or set()
    avisos = []
    cols = _colunas_marcacao(master_df)
    if not cols:
        return avisos

    for idx in range(len(master_df)):
        data_dia = master_df.at[idx, 'Dia']
        if data_dia in datas_ignorar:
            continue
        n = _contar_marcacoes(master_df, idx, cols)
        if n > 0 and n % 2 != 0:
            avisos.append(novo_aviso(
                data=data_dia,
                severidade='warning',
                tipo='jornada_impar',
                mensagem=(
                    f'Jornada incompleta — {n} marcação(ões) (número ímpar). '
                    f'Falta uma entrada ou saída para fechar os pares do dia.'
                ),
            ))
    return avisos


_RE_HHMM_SEQ = re.compile(r'^(\d{1,2}):(\d{2})$')


def _hhmm_para_minutos(valor):
    """Converte 'HH:MM' em minutos. Retorna None para valores nao-horario."""
    m = _RE_HHMM_SEQ.match(str(valor).strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 29 or mi > 59:
        return None
    return h * 60 + mi


def validar_sequencia_cronologica(master_df, datas_ignorar=None, turno_noturno=False, **kwargs):
    """
    Sinaliza dias cuja sequencia de marcacoes RETROCEDE no tempo
    (ex.: ... 17:47 -> 07:30 ...). Em cartao diurno isso indica:
      - linhas de dias diferentes mescladas no mesmo dia (data ilegivel
        no OCR / barra perdida), ou
      - digito trocado pelo OCR (ex.: '17:08' lido no lugar de '07:08').

    IMPORTANTE: o criterio e o RETROCESSO, nao a quantidade de marcacoes.
    Dias legitimamente com varios pares (5+ entradas/saidas) tem horarios
    sempre crescentes e NUNCA disparam este aviso.

    Jobs de turno noturno sao ignorados (turno_noturno=True): plantoes que
    viram a madrugada tem saida menor que a entrada por natureza, e o
    noturno_pareamento.py ja reordena e sinaliza esses casos por conta
    propria.
    """
    if turno_noturno:
        return []

    datas_ignorar = datas_ignorar or set()
    avisos = []
    cols = _colunas_marcacao(master_df)
    if not cols:
        return avisos

    # Ordena colunas por (numero do par, Entrada antes de Saida)
    def _ordem(col):
        m = _RE_MARCACAO.match(str(col))
        num = int(re.sub(r'[^\d]', '', str(col)) or 0)
        tipo = 0 if str(col).startswith('Entrada') else 1
        return (num, tipo)

    cols_ord = sorted(cols, key=_ordem)

    for idx in range(len(master_df)):
        data_dia = master_df.at[idx, 'Dia']
        if data_dia in datas_ignorar:
            continue

        anterior = None
        col_anterior = None
        for col in cols_ord:
            atual = _hhmm_para_minutos(master_df.at[idx, col])
            if atual is None:
                continue
            if anterior is not None and atual < anterior:
                h_ant = '%02d:%02d' % (anterior // 60, anterior % 60)
                h_atu = '%02d:%02d' % (atual // 60, atual % 60)
                avisos.append(novo_aviso(
                    data=data_dia,
                    severidade='danger',
                    tipo='sequencia_retrocede',
                    mensagem=(
                        'Sequencia de horarios retrocede '
                        '({}={} -> {}={}). Possivel digito trocado pelo OCR '
                        'ou linhas de dias diferentes mescladas no mesmo dia '
                        '- confira esta data no PDF original.'
                    ).format(col_anterior, h_ant, col, h_atu),
                ))
                break  # um aviso por dia basta
            anterior = atual
            col_anterior = col
    return avisos


# =====================================================================
# REGISTRO DE VALIDADORES  <-  adicione novos tipos de aviso aqui
# =====================================================================

VALIDADORES = [
    validar_jornada_impar,
    validar_sequencia_cronologica,
    # validar_outro_caso,   # <- futuros validadores entram aqui
]


def coletar_avisos(master_df, datas_ignorar=None, **kwargs):
    """Executa todos os validadores registrados; um que falhe nao derruba os demais."""
    todos = []
    for validador in VALIDADORES:
        try:
            todos.extend(validador(master_df, datas_ignorar=datas_ignorar, **kwargs) or [])
        except Exception as e:
            print(f"[AVISOS] Validador '{validador.__name__}' falhou: {e}", flush=True)
    return todos
