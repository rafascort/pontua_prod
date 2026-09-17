# -*- coding: utf-8 -*-
# /opt/pontua/AutoPonto/backend_api/pericias_email_leitor.py
"""
Leitura de email de servico particular. Zero IA, zero adivinhacao.

MEDIDO CONTRA O MATERIAL REAL DO LUCAS (14/09/2026): 49 de 50 — os 16 prints
da caixa dele (18 e-mails, 5 mensagens de WhatsApp lidas uma a uma), 13
mensagens transcritas, o encaminhado cru em PDF e 11 casos que precisam ser
recusados. A primeira versao acertava 6 de 13.

O unico caso que ainda erra e' uma transcricao incompleta — o mesmo e-mail,
lido do print inteiro, acerta. Com o remetente ja' na lista de conhecidos,
50 de 50.

O corpus vive em prova/casos.py, prova/negativos.py, prova/real_fwd.py e
prova/prints.py. Mudou o leitor, roda `python3 prova/medir_prints.py` antes de
subir.

MUDOU NA v5: com CNJ trabalhista + data escrita + vocabulario de calculo, nao
se exige mais prova de que o remetente e' advogado. Tres dos quatro advogados
que escrevem para o Lucas usam gmail, e um deles nao assina OAB nem escreve
"advogada" em lugar nenhum — a exigencia derrubava 12 servicos reais e nao
barrava uma unica newsletter (newsletter nao carrega CNJ). Em troca entrou a
lista de remetentes conhecidos: endereco de onde o perito ja' aceitou servico
nao precisa provar nada de novo.

O problema: cada advogado escreve de um jeito. Um poe o numero no assunto,
outro so' no corpo, outro so' no nome do PDF anexo. Um escreve "PZ 15/09/26",
outro "PRAZO: 10/09", outro "Pz. 12/08", outro "fatal 18/09".

A saida: o que varia e' a diagramacao, nao o conteudo. Todo email de servico
carrega as mesmas tres coisas, em algum lugar:

    1. um numero CNJ           -> diz que e' processo, e de que Justica
    2. uma data marcada        -> "PZ", "PRAZO", "fatal", "prazo e'"
    3. um advogado no remetente

Entao nao se tenta entender o formato. Procura-se as tres coisas em qualquer
lugar da mensagem - assunto, corpo, nome do anexo - e conta-se quantas
apareceram.
"""

import re
import unicodedata
from datetime import date


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def normalizar(texto):
    return re.sub(r"\s+", " ", sem_acento(texto or "")).strip().lower()


# ------------------------------------------------------------------ numero CNJ
# Limite por "nao ser digito", nao por \b. Em
# "PROCESSO_00201872720255040451_CALCULO_76_DATA..." — o nome que o PJe-Calc
# gera — o \b nao dispara, porque "_" tambem e' caractere de palavra, e o
# numero (sem separador nenhum) passava despercebido.
_RE_CNJ = re.compile(
    r"(?<!\d)(\d{7})[-\s]?(\d{2})[.\s]?(\d{4})[.\s]?(\d)[.\s]?(\d{2})[.\s]?(\d{4})(?!\d)")

RAMOS = {"1": "Federal", "2": "Militar da União", "3": "Militar estadual",
         "4": "Eleitoral", "5": "Trabalho", "6": "Militar", "8": "Estadual", "9": "Estadual"}


def numeros(texto):
    achados = []
    for m in _RE_CNJ.finditer(texto or ""):
        n = "%s-%s.%s.%s.%s.%s" % m.groups()
        if n not in achados:
            achados.append(n)
    return achados


def ramo(numero):
    return RAMOS.get(numero[16:17], "")


# ------------------------------------------------------------------- data do prazo
# Medido nos 13 casos reais do Lucas. Cada pedaco desta expressao existe por
# causa de uma mensagem que de fato chegou:
#
#   "PZ 15/09/26"                                    palavra + data
#   "Pz. 12/08"                                      ponto depois da palavra
#   "PRAZO 21.09"                                    ponto separando dia e mes
#   "fatal 18/09"                                    o WhatsApp usa "fatal"
#   "prazo e' 14/09"                                 uma palavra no meio
#   "prazo ate' o dia 21/09/2026"                    tres palavras no meio
#   "Prazo para apresentar impugnacao aos calculos dia 12/08"   seis palavras
#
# As palavras do meio sao limitadas a oito e nao podem atravessar quebra de
# linha: sem isso a expressao alcancaria a data de qualquer outro paragrafo.
_RE_PRAZO = re.compile(
    r"\b(?:pz|prazo|fatal|entrega|vencimento|data limite)\b"
    r"[^\S\n]*[:\-–.]?[^\S\n]*"
    r"(?:[a-zà-ú]{1,14}[^\S\n]+){0,8}?"
    r"(\d{1,2})[^\S\n]*[/.\-][^\S\n]*(\d{1,2})"
    r"(?:[^\S\n]*[/.\-][^\S\n]*(\d{2,4}))?", re.I)


def prazo(texto, hoje=None):
    hoje = hoje or date.today()
    m = _RE_PRAZO.search(texto or "")
    if not m:
        return None
    d, mes, a = int(m.group(1)), int(m.group(2)), m.group(3)
    if a:
        a = int(a)
        ano = a if a > 100 else 2000 + a
    else:
        ano = hoje.year
    try:
        alvo = date(ano, mes, d)
    except ValueError:
        return None
    if not a and (hoje - alvo).days > 60:
        try:
            alvo = date(ano + 1, mes, d)
        except ValueError:
            return None
    return alvo


# ---------------------------------------------------------------- quem mandou
_RE_OAB = re.compile(r"\boab\s*[/\-]?\s*[a-z]{2}\s*[:\-]?\s*[\d.]{4,}", re.I)
_RE_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_RE_EMAIL_TODO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

DOMINIO_PESSOAL = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
                   "live.com", "icloud.com", "bol.com.br", "uol.com.br", "terra.com.br"}

# Advogado que trabalha em escritorio de verdade e usa Gmail existe, e apareceu
# no primeiro lote: Camila de Biasi Alflen <camiladebiasialflen@gmail.com>,
# assinando "Advogada - Irineu Gehlen Advogados Associados". Nao tem dominio
# proprio nem numero de OAB — tem a profissao escrita por extenso.
#
# Por isso a busca e' restrita a ASSINATURA, os ultimos caracteres da mensagem.
# Solta pelo corpo inteiro, qualquer boletim juridico que fale de advogados
# passaria a se identificar como um.
_RE_PROFISSAO = re.compile(
    r"\b(?:advogad[oa]s?|advocacia|advogados associados|"
    r"sociedade de advogados|escrit[oó]rio de advocacia)\b", re.I)

TAM_ASSINATURA = 500


def assinatura(corpo):
    return (corpo or "")[-TAM_ASSINATURA:]


def endereco(remetente):
    m = _RE_EMAIL_TODO.search(remetente or "")
    return m.group(0).lower() if m else ""


def remetente_advogado(remetente, corpo, origem="email", conhecidos=None):
    # Um endereco de onde o perito ja' aceitou servico nao precisa provar nada
    # de novo. E' o unico jeito honesto de cobrir a advogada que usa gmail e
    # nao assina: da' primeira vez ela cai em "confirmar", o perito aceita, e
    # a partir dai' ela e' conhecida. O sistema aprende com o uso em vez de
    # adivinhar pelo dominio.
    if conhecidos and endereco(remetente) in conhecidos:
        return True, "ja' aceito antes"
    # No WhatsApp nao existe remetente com dominio: quem manda e' um contato da
    # agenda do perito, e um contato salvo ja' e' identificacao suficiente. O
    # canal carrega a identidade que o cabecalho de e-mail carregaria.
    if origem == "whatsapp":
        return True, "contato do WhatsApp"
    if _RE_OAB.search(corpo or "") or _RE_OAB.search(remetente or ""):
        return True, "OAB na assinatura"
    achou = _RE_PROFISSAO.search(assinatura(corpo))
    if achou:
        return True, 'assinou como "%s"' % achou.group(0)
    m = _RE_EMAIL.search(remetente or "")
    if m and m.group(1).lower() not in DOMINIO_PESSOAL:
        return True, "dominio proprio (%s)" % m.group(1)
    return False, ""


# --------------------------------------------------------------- que servico e'
FAZ_CONTA = [
    # `(?![a-zà-ú])` no lugar de `\b`: em "CALCULO_1908952.PJC" o `\b` nao
    # dispara, porque "_" tambem e' caractere de palavra.
    r"c[aá]lculos?(?![a-zà-ú])", r"calcular",
    r"\.pjc\b", r"pje-?calc", r"liquida[çc][aã]o", r"liquidar",
    r"impugna[çc][aã]o", r"amostragem", r"planilha", r"atualiza[çc][aã]o",
    r"contadoria", r"conta de liquida[çc][aã]o", r"quantum", r"apura[çc][aã]o",
    r"agravo de peti[çc][aã]o", r"embargos? [àa] execu[çc][aã]o", r"diferen[çc]as",
    r"horas extras", r"\bfgts\b", r"verbas", r"reflexos", r"honor[aá]rios",
    r"per[ií]cia cont[aá]bil", r"laudo", r"parecer", r"assistente t[eé]cnico",
    r"retificar", r"confer[eê]ncia", r"esclarecimento",
]
OUTRO_PERITO = [
    r"insalubridade", r"periculosidade", r"per[ií]cia m[eé]dica", r"grafot[eé]cnic",
    r"engenharia", r"ergonom", r"ambiental", r"avalia[çc][aã]o de im[oó]vel",
    r"ru[ií]do", r"agente nocivo",
]
_RE_CONTA = re.compile("|".join(FAZ_CONTA), re.I)
_RE_OUTRO = re.compile("|".join(OUTRO_PERITO), re.I)

# "JOEL x SEREDE": nome de quatro letras. O minimo anterior era cinco e
# descartava a unica identificacao que aquela mensagem tinha.
# Alguem esta' me MANDANDO algo para fazer. Sem numero de processo, este e' o
# que separa "Segue inicial de Bruna Amalia Chagas X Serede para elaboracao de
# calculos" de uma newsletter que fala de calculos trabalhistas.
_RE_ENVIO = re.compile(
    r"\b(?:segue[mn]?|encaminho|encaminhando|encaminhei|"
    r"estou (?:te )?(?:mandando|enviando)|em anexo|anexo (?:o|a|os|as)|"
    r"aqui (?:o|a|os|as|vai|est[aá])|"
    r"para (?:elabora|fazer|calcul|impugna|amostr|atualiz|contramin))", re.I)

_RE_PARTES = re.compile(r"([A-ZÀ-Ú][A-Za-zÀ-ú.'\- ]{2,60}?)\s+(?:x|vs\.?|×)\s+([A-ZÀ-Ú][A-Za-zÀ-ú.'\- ]{3,60})")


def _limpa_parte(s, lado="direito"):
    """No assunto o advogado emenda tudo com hifen:
    "Elaboracao de calculos - ALTEMIR SAMPAIO x GKN - 0020187-27...".

    O nome da parte de baixo (esquerda do "x") e' o ULTIMO pedaco antes do "x";
    o de cima (direita) e' o PRIMEIRO depois. Pegar sempre o primeiro punha
    "Elaboracao de calculos" como reclamante."""
    pedacos = [x.strip(" -") for x in re.split(r"\s[-–]\s", (s or "").strip(" -")) if x.strip(" -")]
    if not pedacos:
        return ""
    return pedacos[-1] if lado == "esquerdo" else pedacos[0]


def partes(assunto, corpo):
    m = _RE_PARTES.search(assunto or "") or _RE_PARTES.search(corpo or "")
    if m:
        return _limpa_parte(m.group(1), "esquerdo"), _limpa_parte(m.group(2))
    r = re.search(r"reclamante\s*:?\s*([^\n]{3,60})", corpo or "", re.I)
    d = re.search(r"reclamad[ao]\s*:?\s*([^\n]{3,60})", corpo or "", re.I)
    if r or d:
        return (r.group(1).strip() if r else ""), (d.group(1).strip() if d else "")
    return "", ""


# ------------------------------------------------------- mensagem encaminhada
# Quando o perito encaminha, o "De:" do envelope passa a ser ELE — e o endereco
# dele pode ser pessoal (o Lucas usa hotmail). O advogado fica dentro do corpo,
# num bloco de cabecalho que cada programa escreve de um jeito:
#
#   iOS Mail   "Inicio da mensagem encaminhada:" + De:/Data:/Para:/Assunto:
#   Outlook    De:/Enviado:/Para:/Assunto:
#   Gmail      "---------- Forwarded message ---------" + De:/Data:/Assunto:/Para:
#
# O que interessa e' so' a linha "De:". O pedido original e' o bloco mais FUNDO
# da pilha — a mensagem mais antiga da conversa.
_RE_DE = re.compile(r"^[ \t>]*(?:De|From|Remetente)\s*:\s*(.+?)\s*$", re.M | re.I)


def remetentes_do_corpo(corpo):
    """Todos os "De:" citados no corpo, do mais recente para o mais antigo."""
    return [x.strip() for x in _RE_DE.findall(corpo or "") if x.strip()]


# --------------------------------------------------------------------- leitura

def ler(assunto="", corpo="", remetente="", anexos=None, hoje=None,
        origem="email", conhecidos=None):
    conhecidos = {x.lower() for x in (conhecidos or [])}
    anexos = anexos or []
    tudo = "\n".join([assunto or "", corpo or ""] + list(anexos))
    sinais, contra = [], []

    achados = numeros(tudo)
    onde = ("assunto" if numeros(assunto) else
            "corpo" if numeros(corpo) else
            "anexo" if achados else "")
    numero = achados[0] if achados else None

    if numero:
        sinais.append("numero de processo no %s" % onde)
    if len(achados) > 1:
        contra.append("%d numeros diferentes na mesma mensagem" % len(achados))

    just = ramo(numero) if numero else ""
    if numero and just != "Trabalho":
        contra.append("Justica %s, nao trabalhista" % (just or "desconhecida"))

    fim = prazo(tudo, hoje)
    if fim:
        sinais.append("prazo escrito: %s" % fim.strftime("%d/%m/%Y"))

    citados = remetentes_do_corpo(corpo)
    remetente_real = remetente
    if citados:
        # O mais fundo e' quem comecou a conversa: o advogado que pediu.
        original = citados[-1]
        if not remetente_advogado(original, "", origem, conhecidos)[0] and len(citados) > 1:
            original = next((c for c in reversed(citados)
                             if remetente_advogado(c, "", origem, conhecidos)[0]), original)
        remetente_real = original
        sinais.append("encaminhado; remetente original: %s" % original)

    adv, motivo = remetente_advogado(remetente_real, corpo, origem, conhecidos)
    if adv:
        sinais.append("remetente %s" % motivo)

    if len(citados) > 1:
        # Conversa inteira, nao uma mensagem. O pedido pode ja' ter sido
        # cumprido mais acima na pilha — foi o que aconteceu no primeiro
        # encaminhado real: o Pedro pediu em 01/09, o Lucas entregou em 10/09, e
        # o e-mail traz as tres mensagens. Ler so' o pedido criaria um prazo
        # para trabalho ja' feito.
        contra.append("conversa com %d mensagens: confira se ja' foi entregue" % len(citados))

    tarefas = sorted({normalizar(x.group(0)) for x in _RE_CONTA.finditer(tudo)})
    if tarefas:
        sinais.append("servico de calculo: %s" % ", ".join(tarefas[:3]))
    if _RE_OUTRO.search(tudo):
        contra.append("fala de pericia de outra area")

    a, b = partes(assunto, corpo)

    # A REGRA.
    #
    # Com numero de processo, ele decide quase tudo: ninguem manda newsletter
    # com um CNJ dentro, e o digito 13 diz a Justica.
    #
    # SEM numero e' onde mora a dificuldade — e nao da' para simplesmente
    # descartar: 44% do trabalho do Lucas chega sem numero, e a planilha dele
    # nao tem numero em linha nenhuma. "Segue inicial de Bruna Amalia Chagas X
    # Serede para elaboracao de calculos" e' servico real.
    #
    # Mas afrouxar so' isso deixou entrar newsletter do Migalhas e propaganda de
    # software juridico, porque `migalhas.com.br` tambem e' "dominio proprio" —
    # dominio nao prova advogado. Entao, sem numero, exige-se as tres juntas:
    #
    #   1. remetente identificavel        (dominio proprio, OAB, ou contato)
    #   2. vocabulario de calculo         (o que fazer)
    #   3. partes do processo OU verbo de envio  (estao me pedindo algo)
    #
    # A terceira e' a que derruba a propaganda: ninguem escreve "segue o
    # processo do FULANO x EMPRESA" num e-mail de marketing.
    pedido = bool(_RE_ENVIO.search(tudo))
    identificado = bool(numero) or bool(a and b)

    if numero and just != "Trabalho":
        faixa = "ignorar"
    elif numero:
        # Com CNJ da Justica do Trabalho + data escrita + vocabulario de
        # calculo, exigir tambem prova de que o remetente e' advogado nao
        # filtra nada e derruba gente de verdade: dos quatro advogados que
        # escrevem para o Lucas por e-mail, TRES usam gmail, e a Malu nao
        # assina OAB nem escreve "advogada" em lugar nenhum. Nenhuma
        # newsletter carrega um numero CNJ; o filtro cobrava um pedagio de
        # quem paga e deixava passar quem nao paga.
        if contra:
            faixa = "confirmar"
        elif fim and tarefas:
            faixa = "entra"
        else:
            faixa = "confirmar"
    elif not (adv and tarefas and (identificado or pedido)):
        faixa = "ignorar"
    elif origem == "whatsapp" and not fim:
        # No WhatsApp o contato e' conhecido por definicao, entao a identidade
        # nao filtra nada. O que sustenta a linha e' haver uma data dita.
        faixa = "ignorar"
    elif contra:
        faixa = "confirmar"
    elif fim and identificado:
        faixa = "entra"
    else:
        faixa = "confirmar"

    if not numero and faixa != "ignorar":
        contra.append("sem numero de processo na mensagem")

    return {
        "faixa": faixa,
        "numero": numero,
        "onde_achou": onde,
        "justica": just,
        "prazo": fim.isoformat() if fim else None,
        "reclamante": a,
        "reclamado": b,
        "tarefas": tarefas,
        "remetente_advogado": adv,
        "sinais": sinais,
        "contra": contra,
        "outros_numeros": achados[1:],
        "identificado": identificado,
        "origem": origem,
    }
