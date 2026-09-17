# /opt/pontua/AutoPonto/backend_api/pericias_pje.py
"""
Recebe o retrato do PJe que o favorito do navegador manda.

  POST /api/pericias/pje           <- vem do favorito, rodando DENTRO do PJe
  POST /api/pericias/pje/arquivo   <- mesmo conteudo, subido a mao (JWT, admin)
  GET  /api/pericias/pje/envios    <- o log: o que chegou, quando, de onde

POR QUE O PRIMEIRO NAO TEM LOGIN

O favorito roda na aba do PJe. Ali nao existe sessao do Sistema Ponto — sao
dominios diferentes, e cookie de um dominio nao viaja para o outro. Quem diz
"isto e' do fulano" e' o token que o proprio fulano gerou e que esta' escrito
dentro do favorito dele.

O token e' de MAO UNICA: com ele so' se consegue MANDAR dados para a conta do
dono. Nao le nada, nao autentica em lugar nenhum, nao serve de senha. O pior
caso de um token vazado e' alguem sujar o painel do dono com dado falso — e o
dono conserta sorteando outro token, que invalida o anterior.

CORS SEM PREFLIGHT — a parte que precisa de cuidado

O queue_manager registra CORS em /api/* liberando so' os dominios do
sistemaponto. Um POST com Content-Type: application/json dispara preflight
(OPTIONS), o flask_cors responde sem liberar a origem do PJe, e o navegador
bloqueia antes de a requisicao sair.

A saida nao e' afrouxar o CORS global — e' nao disparar preflight. Um POST com
Content-Type text/plain, sem cabecalho customizado, e' "simple request": o
navegador manda direto. Por isso o token vai NO CORPO e nao num cabecalho, e o
corpo e' lido cru com get_data() em vez de get_json().

Token no corpo tambem mantem ele fora do log do nginx, que registra a URL.

O Access-Control-Allow-Origin da resposta e' devolvido a mao, so' para origem
terminada em .jus.br, e serve unicamente para o favorito conseguir LER a
resposta e dizer ao perito quantas pericias subiram.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import jsonify, make_response, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import text

# 4 MB. O retrato do Lucas — 568 processos — da' algumas centenas de KB.
LIMITE_BYTES = 4 * 1024 * 1024

# Envios por usuario por hora. Coleta normal sao 2 por dia.
LIMITE_HORA = 30

LISTAS = ("vivas", "finalizadas", "arquivadas", "intimacoes")

SQL_TABELA = """
create table if not exists pericia_pje_envio (
    id              bigserial primary key,
    user_id         integer not null references "user"(id) on delete cascade,
    tribunal        text    not null default '',
    perito_pje      text    not null default '',
    origem          text    not null default '',
    via             text    not null default 'favorito',
    bytes           integer not null default 0,
    qtd_vivas       integer not null default 0,
    qtd_finalizadas integer not null default 0,
    qtd_arquivadas  integer not null default 0,
    qtd_intimacoes  integer not null default 0,
    dados           jsonb   not null,
    recebido_em     timestamptz not null default now()
)
"""

SQL_INDICE = """
create index if not exists pericia_pje_envio_user_idx
    on pericia_pje_envio (user_id, recebido_em desc)
"""


def _origem_de_tribunal(origin: str) -> bool:
    """Só .jus.br. Origem vazia (curl, teste) nao ganha cabecalho, mas o POST
    continua valendo — a autorizacao e' o token, nao a origem."""
    try:
        host = (urlparse(origin or "").hostname or "").lower()
    except ValueError:
        return False
    return host.endswith(".jus.br")


def _liberar(resp, origin: str):
    if _origem_de_tribunal(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp


def register_pericias_pje_routes(app):
    from auth_service import User, db

    _pronta = {"tabela": False}

    def _tabela():
        # Igual ao pericias_api: no import ainda nao ha' contexto de aplicacao.
        if not _pronta["tabela"]:
            db.session.execute(text(SQL_TABELA))
            db.session.execute(text(SQL_INDICE))
            db.session.commit()
            _pronta["tabela"] = True

    # ------------------------------------------------------------ guardar

    def _resumo(d):
        return {k: len(d.get(k) or []) for k in LISTAS}

    def _derivar(user_id, d, envio_id):
        """Alimenta a tabela do painel. Procurada na hora da chamada, nao no
        registro, para nao depender da ordem em que os modulos sobem. Se o
        painel nao estiver carregado, o retrato fica guardado do mesmo jeito —
        o /painel/refazer recupera depois."""
        try:
            f = (app.extensions.get("pericias") or {}).get("gravar_painel")
            if f:
                f(user_id, d, envio_id)
        except Exception as e:
            print("[PERICIAS-PJE] retrato guardado, derivacao falhou:", e)

    def _guardar(user_id, d, bruto, origem, via):
        q = _resumo(d)
        db.session.execute(
            text("""
                insert into pericia_pje_envio
                    (user_id, tribunal, perito_pje, origem, via, bytes,
                     qtd_vivas, qtd_finalizadas, qtd_arquivadas, qtd_intimacoes, dados)
                values
                    (:u, :tb, :pe, :o, :vi, :by, :qv, :qf, :qa, :qi, cast(:dj as jsonb))
            """),
            {
                "u": user_id,
                "tb": str(d.get("tribunal") or "")[:40],
                "pe": str(d.get("perito") or "")[:160],
                "o": (origem or "")[:200],
                "vi": via,
                "by": len(bruto),
                "qv": q["vivas"], "qf": q["finalizadas"],
                "qa": q["arquivadas"], "qi": q["intimacoes"],
                "dj": json.dumps(d, ensure_ascii=False),
            },
        )
        db.session.commit()
        envio_id = db.session.execute(
            text("select id from pericia_pje_envio where user_id = :u"
                 " order by recebido_em desc limit 1"),
            {"u": user_id},
        ).scalar()
        _derivar(user_id, d, envio_id)
        return q

    def _conferir_ritmo(user_id):
        n = db.session.execute(
            text("select count(*) from pericia_pje_envio"
                 " where user_id = :u and recebido_em > now() - interval '1 hour'"),
            {"u": user_id},
        ).scalar() or 0
        return n < LIMITE_HORA

    def _validar_corpo(bruto):
        """(dados, erro). Recusa o que nao tem cara de retrato do PJe."""
        if not bruto:
            return None, "Corpo vazio."
        if len(bruto) > LIMITE_BYTES:
            return None, "Retrato grande demais."
        try:
            corpo = json.loads(bruto)
        except (ValueError, TypeError):
            return None, "Corpo não é JSON."
        if not isinstance(corpo, dict):
            return None, "Formato inesperado."
        return corpo, None

    # ------------------------------------------------------------- favorito

    @app.route("/api/pericias/pje", methods=["POST", "OPTIONS"])
    def pericias_pje_receber():
        origin = request.headers.get("Origin", "")

        if request.method == "OPTIONS":
            # Nao deveria acontecer: o favorito manda text/plain, que e' simple
            # request. Fica aqui para o caso de algum navegador decidir o
            # contrario, em vez de o recurso morrer sem explicacao.
            r = make_response("", 204)
            r.headers["Access-Control-Allow-Methods"] = "POST"
            r.headers["Access-Control-Allow-Headers"] = "Content-Type"
            r.headers["Access-Control-Max-Age"] = "600"
            return _liberar(r, origin)

        if (request.content_length or 0) > LIMITE_BYTES:
            return _liberar(jsonify({"msg": "Retrato grande demais."}), origin), 413

        _tabela()

        bruto = request.get_data(cache=False, as_text=True)
        corpo, erro = _validar_corpo(bruto)
        if erro:
            return _liberar(jsonify({"msg": erro}), origin), 400

        token = str(corpo.get("token") or "")
        dados = corpo.get("dados")
        if not token or not isinstance(dados, dict):
            return _liberar(jsonify({"msg": "Envio incompleto."}), origin), 400

        # Token curto nem consulta o banco.
        if not (20 <= len(token) <= 120):
            return _liberar(jsonify({"msg": "Token inválido."}), origin), 401

        dono = db.session.execute(
            text("select user_id from pericia_perito where token_pje = :t"),
            {"t": token},
        ).first()
        if not dono:
            return _liberar(jsonify({"msg": "Token inválido ou revogado."}), origin), 401

        if not _conferir_ritmo(dono.user_id):
            return _liberar(jsonify({"msg": "Muitos envios seguidos. Tente daqui a pouco."}), origin), 429

        q = _guardar(dono.user_id, dados, bruto, origin, "favorito")
        return _liberar(jsonify({"ok": True, **q}), origin), 200

    # -------------------------------------------------------------- arquivo

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

    @app.route("/api/pericias/pje/arquivo", methods=["POST"])
    @jwt_required()
    def pericias_pje_arquivo():
        """Plano B do favorito: se o PJe bloquear a chamada por CSP, o favorito
        baixa o arquivo e o perito sobe por aqui. Mesmo destino, mesma tabela."""
        u, erro = _admin()
        if erro:
            return erro
        if (request.content_length or 0) > LIMITE_BYTES:
            return jsonify({"msg": "Arquivo grande demais."}), 413

        bruto = request.get_data(cache=False, as_text=True)
        dados, msg = _validar_corpo(bruto)
        if msg:
            return jsonify({"msg": msg}), 400
        if not any(k in dados for k in LISTAS):
            return jsonify({"msg": "Este arquivo não parece um retrato do PJe."}), 400

        q = _guardar(u.id, dados, bruto, "upload", "arquivo")
        return jsonify({"ok": True, **q}), 200

    # ------------------------------------------------------------------ log

    @app.route("/api/pericias/pje/envios", methods=["GET"])
    @jwt_required()
    def pericias_pje_envios():
        """So' o cabecalho de cada envio. O conteudo nao volta para a tela —
        ela nao precisa dele, e trafegar megabyte a' toa e' ruim de graca."""
        u, erro = _admin()
        if erro:
            return erro
        linhas = db.session.execute(
            text("select id, tribunal, perito_pje, via, bytes, qtd_vivas,"
                 " qtd_finalizadas, qtd_arquivadas, qtd_intimacoes, recebido_em"
                 " from pericia_pje_envio where user_id = :u"
                 " order by recebido_em desc limit 20"),
            {"u": u.id},
        ).all()
        return jsonify({
            "envios": [{
                "id": l.id,
                "tribunal": l.tribunal,
                "perito_pje": l.perito_pje,
                "via": l.via,
                "bytes": l.bytes,
                "vivas": l.qtd_vivas,
                "finalizadas": l.qtd_finalizadas,
                "arquivadas": l.qtd_arquivadas,
                "intimacoes": l.qtd_intimacoes,
                "recebido_em": l.recebido_em.isoformat() if l.recebido_em else None,
            } for l in linhas]
        }), 200
