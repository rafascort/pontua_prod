# /opt/pontua/AutoPonto/backend_api/pericias_painel.py
"""
Transforma o retrato cru do PJe na tabela que o painel le'.

  pericia_processo   uma linha por PERICIA (nao por processo)
  pericia_marcacao   o que o PERITO escreveu: baixa e observacao
  GET  /api/pericias/painel            o que o painel mostra
  PUT  /api/pericias/pericia/<id>      baixa e observacao
  POST /api/pericias/painel/refazer    re-deriva o ultimo retrato guardado

O PJE E' A FONTE DA VERDADE. O SISTEMA NAO OPINA.

  Versao anterior tentava adivinhar "de quem e' a bola" cruzando o campo
  `tarefa` com uma lista de palavras. Errou feio no acervo real:

    - "Elaborar despacho" e "Assinar despacho" sao tarefas do CARTORIO. Estavam
      na lista de "e' com o perito".
    - `prazoEntrega` nao e' prazo vivo: e' fixado uma vez no aceite (aceite +
      ~20 dias) e nunca mais se mexe. Pericias abertas desde 2025 apareciam
      como atraso de 335 dias.
    - Chips automaticos ("confira", "prioridade") viravam ruido: o sistema
      opinando sobre o processo do perito.

  Agora nao ha' classificacao de bola nenhuma. So' o que o PJe declara:

    entregue   situacaoTexto "Laudo Juntado" ou "Finalizada", sem permissao
               pendente de juntar laudo ou esclarecimentos
    encerrada  "Cancelada" ou "Redesignada" — saiu das maos dele
    aberta     todo o resto

  O que separa o prazo de 2025 do prazo de sexta e' o HORIZONTE, nao um
  palpite: por padrao o painel mostra vencidos dos ultimos 60 dias e o que
  vence nos proximos 15 — exatamente o recorte do painel que o perito ja'
  usava. O resto continua existindo e fica a um clique.

  Juizo de valor so' vem do perito, e a mao: baixa ("ja' fiz", "nao e' meu") e
  observacao livre.

DUAS ARMADILHAS DO RETRATO, MEDIDAS EM 2.173 REGISTROS DO TRT4

  1. `arquivadas` NAO e' estado, e' filtro: 631 pericias vem em
     arquivadas+finalizadas, 78 em arquivadas+vivas. Somar as listas conta
     2.173 onde existem 1.464. As copias sao identicas campo a campo, entao
     de-duplicar por idPericia nao perde nada.
  2. `processo` NAO serve de chave: 137 processos tem mais de uma pericia
     distinta, um deles tem sete. A chave e' idPericia.
"""
from __future__ import annotations

import json
import os

from datetime import date, datetime, timedelta, timezone

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import text

ENTREGUE = {"laudo juntado", "finalizada"}

# Saiu das maos do perito sem ele entregar. Cuidado com o par de nomes:
#   "Redesignada"     = tiraram dele          -> encerrada
#   "Nova designação" = deram para ele agora  -> aberta
ENCERRADA = {"cancelada", "redesignada"}

BAIXAS = {"fiz", "nao_meu", "mandaram_nao_fazer", "encerrado"}

# Horizonte padrao, copiado do painel que o perito ja' usava:
# "vencidos sem baixa - ultimos 60 dias" e "vencendo em 5 dias uteis".
DIAS_ATRAS_PADRAO = 60
DIAS_FRENTE_PADRAO = 15

SQL_TABELA = """
create table if not exists pericia_processo (
    id                bigserial primary key,
    user_id           integer not null references "user"(id) on delete cascade,
    id_pericia        bigint  not null,
    id_processo       bigint,
    processo          text    not null,
    tribunal          text    not null default '',
    situacao          text,
    situacao_texto    text,
    tarefa            text,
    classe            text,
    orgao             text,
    partes            text,
    fase              text,
    prazo_entrega     date,
    data_aceite       date,
    data_criacao      date,
    expediente_aberto boolean not null default false,
    ciencia_pendente  boolean not null default false,
    prioridade        boolean not null default false,
    arquivado         boolean not null default false,
    finalizada        boolean not null default false,
    laudo_juntado     boolean not null default false,
    pode_laudo        boolean not null default false,
    pode_esclarecimentos boolean not null default false,
    entregue          boolean not null default false,
    bola              text    not null default 'aberta',
    tarefa_conhecida  boolean not null default true,
    envio_id          bigint,
    atualizado_em     timestamptz not null default now(),
    unique (user_id, id_pericia)
)
"""

SQL_COLUNAS = [
    "alter table pericia_processo add column if not exists laudo_juntado boolean not null default false",
    "alter table pericia_processo add column if not exists pode_laudo boolean not null default false",
    "alter table pericia_processo add column if not exists pode_esclarecimentos boolean not null default false",
]

# O que o PERITO escreveu. Fica FORA de pericia_processo de proposito: aquela
# tabela e' apagada e refeita a cada retrato novo do PJe, e o que ele escreveu
# nao pode sumir junto.
SQL_MARCACAO = """
create table if not exists pericia_marcacao (
    user_id       integer not null references "user"(id) on delete cascade,
    fonte         text    not null default 'pje',
    id_pericia    bigint  not null,
    baixa         text,
    observacao    text,
    atualizado_em timestamptz not null default now(),
    primary key (user_id, fonte, id_pericia)
)
"""

# POR QUE `fonte` EXISTE AQUI
#
# A marcacao e' endereçada por (user_id, id_pericia). O id_pericia do PJe e o
# id da pericia_entrada sao contadores DIFERENTES e independentes: um dia a
# entrada de e-mail nº 5 e a pericia nº 5 do PJe existem as duas, e sem a
# `fonte` elas dividem a mesma linha de marcacao. O perito daria baixa num
# servico de e-mail e um processo do PJe sumiria junto.
#
# Nao e' hipotetico — e' questao de tempo ate' os dois contadores se cruzarem.
# Se alguem "simplificar" isso de volta um dia, esse e' o bug que volta.
SQL_MARCACAO_MIGRA = [
    "alter table pericia_marcacao"
    " add column if not exists fonte text not null default 'pje'",
    """
    do $$
    begin
        if not exists (
            select 1 from pg_index i
              join pg_attribute a on a.attrelid = i.indrelid
                                 and a.attnum = any(i.indkey)
             where i.indrelid = 'pericia_marcacao'::regclass
               and i.indisprimary and a.attname = 'fonte')
        then
            alter table pericia_marcacao drop constraint pericia_marcacao_pkey;
            alter table pericia_marcacao add primary key (user_id, fonte, id_pericia);
        end if;
    end $$;
    """,
]

SQL_INDICE = """
create index if not exists pericia_processo_painel_idx
    on pericia_processo (user_id, bola, prazo_entrega)
"""

SQL_INSERE = """
insert into pericia_processo
    (user_id, id_pericia, id_processo, processo, tribunal, situacao, situacao_texto,
     tarefa, classe, orgao, partes, fase, prazo_entrega, data_aceite, data_criacao,
     expediente_aberto, ciencia_pendente, prioridade, arquivado, finalizada,
     laudo_juntado, pode_laudo, pode_esclarecimentos,
     entregue, bola, tarefa_conhecida, envio_id, atualizado_em)
values
    (:user_id, :id_pericia, :id_processo, :processo, :tribunal, :situacao, :situacao_texto,
     :tarefa, :classe, :orgao, :partes, :fase, :prazo_entrega, :data_aceite, :data_criacao,
     :expediente_aberto, :ciencia_pendente, :prioridade, :arquivado, :finalizada,
     :laudo_juntado, :pode_laudo, :pode_esclarecimentos,
     :entregue, :bola, true, :envio_id, now())
"""


def _hoje():
    """Hoje em Brasilia. O servidor roda em UTC; entre 21h e meia-noite a data
    UTC ja' virou e a daqui nao — diferenca suficiente para um prazo aparecer
    vencido um dia antes."""
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def _data(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _txt(v, n=200):
    return (str(v).strip()[:n] or None) if v not in (None, "") else None


def preparar(dados, user_id, envio_id=None):
    """Retrato cru -> uma linha por idPericia. Sem banco, da' para testar com
    um JSON na mao."""
    juntas = {}

    def entra(lista, marca):
        for x in (dados.get(lista) or []):
            pid = x.get("idPericia")
            if pid is None:
                continue
            linha = juntas.get(pid)
            if linha is None:
                linha = juntas[pid] = dict(x)
                linha["_arquivado"] = False
                linha["_finalizada"] = False
                linha["_ciencia"] = False
            if marca:
                linha["_" + marca] = True
            if x.get("cienciaPendente"):
                linha["_ciencia"] = True

    entra("vivas", None)
    entra("finalizadas", "finalizada")
    entra("arquivadas", "arquivado")
    # A lista de intimacoes traz as mesmas pericias; o que ela acrescenta e' o
    # sinal de ciencia pendente. Nao cria linha nova por conta propria.
    entra("intimacoes", None)

    tribunal = _txt(dados.get("tribunal"), 40) or ""
    saida = []

    for pid, x in juntas.items():
        situacao_texto = _txt(x.get("situacaoTexto"))
        st = (situacao_texto or "").lower()

        finalizada = bool(x["_finalizada"])
        pode_laudo = bool(x.get("podeJuntarLaudo"))
        pode_esclar = bool(x.get("podeJuntarEsclarecimentos"))

        # Tres estados, todos declarados pelo PJe. Nenhum palpite.
        if st in ENCERRADA:
            bola = "encerrada"
        elif (st in ENTREGUE or finalizada) and not (pode_laudo or pode_esclar):
            bola = "entregue"
        else:
            bola = "aberta"

        saida.append({
            "user_id": user_id,
            "id_pericia": int(pid),
            "id_processo": x.get("idProcesso") if isinstance(x.get("idProcesso"), int) else None,
            "processo": _txt(x.get("processo"), 30) or "",
            "tribunal": tribunal,
            "situacao": _txt(x.get("situacao"), 4),
            "situacao_texto": situacao_texto,
            "tarefa": _txt(x.get("tarefa")),
            "classe": _txt(x.get("classe"), 20),
            "orgao": _txt(x.get("orgao"), 200),
            "partes": _txt(x.get("partes"), 400),
            "fase": _txt(x.get("fase"), 80),
            "prazo_entrega": _data(x.get("prazoEntrega")),
            "data_aceite": _data(x.get("dataAceite")),
            "data_criacao": _data(x.get("dataCriacao")),
            "expediente_aberto": bool(x.get("expedienteAberto")),
            "ciencia_pendente": bool(x["_ciencia"]),
            "prioridade": bool(x.get("prioridadeProcessual") or x.get("prioridade")),
            "arquivado": bool(x["_arquivado"]),
            "finalizada": finalizada,
            "laudo_juntado": bool(x.get("laudoJuntado")),
            "pode_laudo": pode_laudo,
            "pode_esclarecimentos": pode_esclar,
            "entregue": bola == "entregue",
            "bola": bola,
            "envio_id": envio_id,
        })

    return [l for l in saida if l["processo"]]


CAMPOS = ("p.id_pericia, p.processo, p.tribunal, p.situacao_texto, p.tarefa, p.classe,"
          " p.orgao, p.partes, p.fase, p.prazo_entrega, p.data_aceite,"
          " p.expediente_aberto, p.ciencia_pendente, p.laudo_juntado,"
          " p.pode_laudo, p.pode_esclarecimentos,"
          " m.baixa, m.observacao,"
          " 'pje' as fonte, 'prazo do PJe' as prazo_rotulo, false as no_acervo,"
          " (p.prazo_entrega - (now() at time zone 'America/Sao_Paulo')::date) as dias")

DE = ("from pericia_processo p"
      " left join pericia_marcacao m"
      "   on m.user_id = p.user_id and m.id_pericia = p.id_pericia"
      "  and m.fonte = 'pje'")

# ---------------------------------------------------------- entrada por e-mail
#
# 44% do trabalho do Lucas nao existe no PJe e nunca vai existir: sao pedidos
# particulares de advogado. O painel que so' le' o PJe cobre pouco mais da
# metade da vida dele.
#
# Essas linhas NAO podem morar em pericia_processo: aquela tabela e' apagada e
# refeita inteira a cada retrato novo do bookmarklet, e o servico do advogado
# sumiria no proximo envio. Entao o painel le' das duas tabelas e junta na hora
# de responder.
#
# So' entra o que o PERITO marcou como aceito. A faixa do leitor ordena a fila
# de triagem; ela nao decide o que vira trabalho. Quem decide e' o clique.
HOJE_SQL = "(now() at time zone 'America/Sao_Paulo')::date"

SQL_EMAIL = (
    "select e.id, e.numero, e.prazo, e.reclamante, e.reclamado, e.remetente,"
    " e.assunto, e.tarefas, e.no_acervo, e.decidido_em,"
    " m.baixa, m.observacao,"
    " (e.prazo - " + HOJE_SQL + ") as dias"
    " from pericia_entrada e"
    " left join pericia_marcacao m"
    "   on m.user_id = e.user_id and m.id_pericia = e.id and m.fonte = 'email'"
    " where e.user_id = :u and e.estado = 'aceito' and %s"
    " order by %s limit %d")


def _servico(tarefas_json):
    try:
        t = json.loads(tarefas_json or "[]")
    except (TypeError, ValueError):
        return None
    return ", ".join(str(x) for x in t[:3]) or None


def _linha_email(r):
    """A linha de e-mail sai com os MESMOS nomes de coluna da linha do PJe.
    O frontend desenha uma tabela so'; quem diz de onde veio e' `fonte`, e o
    que a data significa e' `prazo_rotulo` — que vai nas duas justamente para
    o perito nunca ter que lembrar qual e' qual."""
    partes = " x ".join(x for x in (r.reclamante, r.reclamado) if x) or None
    return {
        "id_pericia": r.id,
        "fonte": "email",
        "processo": r.numero or "",
        "tribunal": "",
        "situacao_texto": "pedido de advogado",
        "tarefa": _servico(r.tarefas) or (r.assunto or None),
        "classe": None,
        "orgao": r.remetente or None,          # onde o olho procura "de onde veio"
        "partes": partes,
        "fase": None,
        "prazo_entrega": r.prazo.isoformat() if r.prazo else None,
        "prazo_rotulo": "prazo dado pelo advogado",
        "data_aceite": r.decidido_em.date().isoformat() if r.decidido_em else None,
        "expediente_aberto": False,
        "ciencia_pendente": False,
        "laudo_juntado": False,
        "pode_laudo": False,
        "pode_esclarecimentos": False,
        "no_acervo": bool(r.no_acervo),
        "assunto": r.assunto or None,
        "baixa": r.baixa,
        "observacao": r.observacao,
        "dias": r.dias,
    }


def _juntar(pje, email, chave, desc=False):
    """Cada lado ja' vem ordenado; depois de somar, a ordem tem que valer para
    o conjunto. Linha sem data vai para o fim, nos dois sentidos."""
    todos = list(pje) + list(email)
    com = [d for d in todos if d.get(chave)]
    sem = [d for d in todos if not d.get(chave)]
    com.sort(key=lambda d: d[chave], reverse=desc)
    return com + sem


def _email_ligado():
    return (os.environ.get("PERICIAS_PAINEL_EMAIL", "") or "").strip().lower() in (
        "1", "true", "sim", "on", "yes")


def register_pericias_painel_routes(app):
    from auth_service import User, db

    _pronta = {"ok": False}

    def _tabela():
        if not _pronta["ok"]:
            db.session.execute(text(SQL_TABELA))
            for c in SQL_COLUNAS:
                db.session.execute(text(c))
            db.session.execute(text(SQL_MARCACAO))
            for c in SQL_MARCACAO_MIGRA:
                db.session.execute(text(c))
            db.session.execute(text(SQL_INDICE))
            db.session.commit()
            _pronta["ok"] = True

    def _admin():
        _tabela()
        ident = get_jwt_identity()
        u = User.query.filter_by(email=str(ident)).first() if ident is not None else None
        if not u:
            try:
                u = User.query.get(int(ident))
            except (TypeError, ValueError):
                u = None
        if not u:
            return None, (jsonify({"msg": "Sessão inválida."}), 401)
        if (u.role or "") != "admin":
            return None, (jsonify({"msg": "Módulo em testes: acesso restrito."}), 403)
        return u, None

    def gravar(user_id, dados, envio_id=None):
        """Troca inteira: o retrato novo substitui o anterior. `pericia_marcacao`
        nao e' tocada — o que o perito escreveu sobrevive."""
        _tabela()
        linhas = preparar(dados, user_id, envio_id)
        db.session.execute(text("delete from pericia_processo where user_id = :u"),
                           {"u": user_id})
        if linhas:
            db.session.execute(text(SQL_INSERE), linhas)
        db.session.commit()
        return len(linhas)

    app.extensions.setdefault("pericias", {})["gravar_painel"] = gravar

    def _email(user_id, onde, ordem, limite=300):
        """As linhas de e-mail. Devolve lista VAZIA com o interruptor
        desligado — e' o que faz a alteracao ser inocua ate' o frontend saber
        desenhar a diferenca entre as duas fontes."""
        if not _email_ligado():
            return []
        sql = SQL_EMAIL % (onde.format(h=HOJE_SQL), ordem, limite)
        return [_linha_email(r) for r in
                db.session.execute(text(sql), {"u": user_id}).all()]

    def _kpi_email(user_id, atras, frente):
        if not _email_ligado():
            return None
        return db.session.execute(text("""
            select
              count(*) filter (where m.baixa is null and e.prazo < {h}
                                 and e.prazo >= {h} - {a})                 as vencido,
              count(*) filter (where m.baixa is null and e.prazo >= {h}
                                 and e.prazo <= {h} + {f})                 as correndo,
              count(*) filter (where m.baixa is null and e.prazo is not null
                                 and not (e.prazo >= {h} - {a}
                                      and e.prazo <= {h} + {f}))           as fora,
              count(*) filter (where m.baixa is null and e.prazo is null)  as sem_prazo,
              count(*) filter (where m.baixa is not null)                  as com_baixa,
              count(*)                                                     as total,
              count(*) filter (where e.no_acervo)                          as no_acervo
              from pericia_entrada e
              left join pericia_marcacao m
                on m.user_id = e.user_id and m.id_pericia = e.id and m.fonte = 'email'
             where e.user_id = :u and e.estado = 'aceito'
        """.format(h=HOJE_SQL, a=atras, f=frente)), {"u": user_id}).first()

    def _lista(user_id, onde, ordem, limite=300):
        saida = []
        for r in db.session.execute(
            text("select %s %s where p.user_id = :u and %s order by %s limit %d"
                 % (CAMPOS, DE, onde, ordem, limite)),
            {"u": user_id},
        ).all():
            d = dict(r._mapping)
            for c in ("prazo_entrega", "data_aceite"):
                if d.get(c) is not None:
                    d[c] = d[c].isoformat()
            saida.append(d)
        return saida

    @app.route("/api/pericias/painel", methods=["GET"])
    @jwt_required()
    def pericias_painel():
        u, erro = _admin()
        if erro:
            return erro

        try:
            atras = min(max(int(request.args.get("atras", DIAS_ATRAS_PADRAO)), 0), 3650)
            frente = min(max(int(request.args.get("frente", DIAS_FRENTE_PADRAO)), 1), 3650)
        except (TypeError, ValueError):
            atras, frente = DIAS_ATRAS_PADRAO, DIAS_FRENTE_PADRAO

        cab = db.session.execute(
            text("select tribunal, perito_pje, recebido_em, via from pericia_pje_envio"
                 " where user_id = :u order by recebido_em desc limit 1"),
            {"u": u.id},
        ).first()

        n = db.session.execute(
            text("select count(*) from pericia_processo where user_id = :u"), {"u": u.id}
        ).scalar() or 0

        # Tabela vazia com retrato guardado = derivacao que nao rodou. Refaz
        # sozinho, se nao o painel manda configurar o que ja' esta' configurado.
        if not n:
            guardado = db.session.execute(
                text("select id, dados from pericia_pje_envio where user_id = :u"
                     " order by recebido_em desc limit 1"),
                {"u": u.id},
            ).first()
            if guardado:
                try:
                    n = gravar(u.id, guardado.dados, guardado.id)
                except Exception as e:
                    print("[PERICIAS-PAINEL] derivacao automatica falhou:", e)
                    db.session.rollback()
        if not n:
            return jsonify({"tem_dados": False, "ultimo_envio": None}), 200

        H = "(now() at time zone 'America/Sao_Paulo')::date"
        ABERTA = "p.bola = 'aberta' and m.baixa is null"
        DENTRO = "p.prazo_entrega >= {h} - {a} and p.prazo_entrega <= {h} + {f}".format(
            h=H, a=atras, f=frente)

        c = db.session.execute(
            text("""
                select
                  count(*) filter (where {ab} and p.prazo_entrega <  {h} and p.prazo_entrega >= {h} - {a}) as vencido,
                  count(*) filter (where {ab} and p.prazo_entrega >= {h} and p.prazo_entrega <= {h} + {f}) as correndo,
                  count(*) filter (where {ab} and p.prazo_entrega is not null and not ({dentro})) as fora,
                  count(*) filter (where {ab} and p.prazo_entrega is null) as sem_prazo,
                  count(*) filter (where {ab} and p.pode_esclarecimentos) as esclarecimentos,
                  count(*) filter (where p.expediente_aberto and p.bola <> 'encerrada' and m.baixa is null) as envelope,
                  count(*) filter (where p.ciencia_pendente and m.baixa is null) as ciencia,
                  count(*) filter (where m.baixa is not null) as com_baixa,
                  count(*) filter (where p.bola = 'aberta') as abertas,
                  count(*) filter (where p.bola = 'entregue') as entregue,
                  count(*) filter (where p.bola = 'encerrada') as encerrada,
                  count(*) as total
                {de} where p.user_id = :u
            """.format(ab=ABERTA, h=H, a=atras, f=frente, dentro=DENTRO, de=DE)),
            {"u": u.id},
        ).first()

        ke = _kpi_email(u.id, atras, frente)

        return jsonify({
            "tem_dados": True,
            "horizonte": {"atras": atras, "frente": frente},
            "ultimo_envio": {
                "tribunal": cab.tribunal if cab else "",
                "perito_pje": cab.perito_pje if cab else "",
                "recebido_em": cab.recebido_em.isoformat() if cab and cab.recebido_em else None,
                "via": cab.via if cab else "",
            },
            # O contador tem que bater com a lista. Se o kpi contasse so' o
            # PJe e a lista mostrasse as duas fontes, diria 3 com 5 na tela.
            # `de_email` responde sozinho a pergunta que motivou a juncao:
            # quanto do trabalho do perito o PJe nao enxerga. No acervo do
            # Lucas isso foi 44%.
            "kpi": {
                "vencido": c.vencido + (ke.vencido if ke else 0),
                "correndo": c.correndo + (ke.correndo if ke else 0),
                "fora": c.fora + (ke.fora if ke else 0),
                "sem_prazo": c.sem_prazo + (ke.sem_prazo if ke else 0),
                "esclarecimentos": c.esclarecimentos,
                "envelope": c.envelope, "ciencia": c.ciencia,
                "com_baixa": c.com_baixa + (ke.com_baixa if ke else 0),
                "abertas": c.abertas, "entregue": c.entregue,
                "encerrada": c.encerrada,
                "total": c.total + (ke.total if ke else 0),
                "de_email": (ke.total if ke else 0),
                "email_no_acervo": (ke.no_acervo if ke else 0),
            },
            "vencido":  _juntar(
                _lista(u.id, "%s and p.prazo_entrega < %s and p.prazo_entrega >= %s - %d"
                             % (ABERTA, H, H, atras), "p.prazo_entrega desc"),
                _email(u.id, "m.baixa is null and e.prazo < {h} and e.prazo >= {h} - %d" % atras,
                       "e.prazo desc"),
                "prazo_entrega", desc=True),
            "correndo": _juntar(
                _lista(u.id, "%s and p.prazo_entrega >= %s and p.prazo_entrega <= %s + %d"
                             % (ABERTA, H, H, frente), "p.prazo_entrega asc"),
                _email(u.id, "m.baixa is null and e.prazo >= {h} and e.prazo <= {h} + %d" % frente,
                       "e.prazo asc"),
                "prazo_entrega"),
            "sem_prazo": _juntar(
                _lista(u.id, "%s and p.prazo_entrega is null" % ABERTA,
                       "p.data_aceite desc nulls last"),
                _email(u.id, "m.baixa is null and e.prazo is null", "e.recebido_em desc"),
                "data_aceite", desc=True),
            "esclarecimentos": _lista(u.id, "%s and p.pode_esclarecimentos" % ABERTA,
                                      "p.prazo_entrega asc nulls last"),
            "envelope": _lista(u.id, "p.expediente_aberto and p.bola <> 'encerrada' and m.baixa is null",
                               "p.prazo_entrega desc nulls last"),
            "ciencia": _lista(u.id, "p.ciencia_pendente and m.baixa is null",
                              "p.prazo_entrega desc nulls last"),
            "fora": _lista(u.id, "%s and p.prazo_entrega is not null and not (%s)" % (ABERTA, DENTRO),
                           "p.prazo_entrega asc"),
        }), 200

    @app.route("/api/pericias/pericia/<int:id_pericia>", methods=["PUT"])
    @jwt_required()
    def pericias_marcar(id_pericia):
        """Baixa e observacao. O unico lugar em que o sistema aceita juizo de
        valor — e ele vem do perito, digitado."""
        u, erro = _admin()
        if erro:
            return erro

        d = request.get_json(silent=True) or {}

        # Sem `fonte` no pedido e' PJe: o frontend antigo continua funcionando
        # sem saber que existe outra fonte.
        fonte = str(d.get("fonte") or "pje")
        if fonte not in ("pje", "email"):
            return jsonify({"msg": "Fonte inválida."}), 400

        if fonte == "pje":
            existe = db.session.execute(
                text("select 1 from pericia_processo where user_id = :u and id_pericia = :p"),
                {"u": u.id, "p": id_pericia},
            ).first()
        else:
            existe = db.session.execute(
                text("select 1 from pericia_entrada"
                     " where user_id = :u and id = :p and estado = 'aceito'"),
                {"u": u.id, "p": id_pericia},
            ).first()
        if not existe:
            return jsonify({"msg": "Perícia não encontrada."}), 404

        baixa = d.get("baixa")
        if baixa in ("", None):
            baixa = None
        elif str(baixa) not in BAIXAS:
            return jsonify({"msg": "Baixa inválida."}), 400

        obs = d.get("observacao")
        obs = None if obs in ("", None) else str(obs).strip()[:2000] or None

        db.session.execute(
            text("""
                insert into pericia_marcacao
                    (user_id, fonte, id_pericia, baixa, observacao, atualizado_em)
                values (:u, :f, :p, :b, :o, now())
                on conflict (user_id, fonte, id_pericia) do update set
                    baixa = :b, observacao = :o, atualizado_em = now()
            """),
            {"u": u.id, "f": fonte, "p": id_pericia, "b": baixa, "o": obs},
        )
        db.session.commit()
        return jsonify({"ok": True, "fonte": fonte,
                        "baixa": baixa, "observacao": obs}), 200

    @app.route("/api/pericias/painel/refazer", methods=["POST"])
    @jwt_required()
    def pericias_painel_refazer():
        u, erro = _admin()
        if erro:
            return erro
        linha = db.session.execute(
            text("select id, dados from pericia_pje_envio where user_id = :u"
                 " order by recebido_em desc limit 1"),
            {"u": u.id},
        ).first()
        if not linha:
            return jsonify({"msg": "Nenhum retrato do PJe recebido ainda."}), 400
        return jsonify({"ok": True, "pericias": gravar(u.id, linha.dados, linha.id)}), 200
