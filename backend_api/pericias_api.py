# /opt/pontua/AutoPonto/backend_api/pericias_api.py
"""
Modulo Pericias — cadastro do perito e token do PJe.

Tres endpoints, todos sob /api/pericias e todos restritos a admin enquanto o
modulo esta' em testes:

  GET    /api/pericias/perito         le a configuracao do proprio usuario
  PUT    /api/pericias/perito         grava a configuracao
  POST   /api/pericias/perito/token   sorteia (ou re-sorteia) o token do PJe

DESENHO DE RISCO

  1. Nao cria model do SQLAlchemy e nao mexe em Alembic. Fala com a tabela por
     SQL puro. O repositorio pode ter migration pendente que nunca rodou no
     servidor, e um `upgrade head` aplicaria todas de uma vez — risco que nao
     tem nada a ver com este modulo.
  2. So' cria tabela nova (`pericia_perito`). Nao altera `user` nem nenhuma
     outra que os clientes usem.
  3. Autocontido: faz a propria checagem de admin, como o email_admin_api.
  4. Registrar com register_pericias_routes(app) dentro de try/except.

O token do PJe e' um segredo de MAO UNICA: com ele so' se consegue MANDAR
pericias para a conta do dono. Nao le nada, nao autentica em lugar nenhum.
Por isso pode viver num favorito do navegador — o pior caso e' alguem sujar o
painel com dado falso, e o dono revoga sorteando outro.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import text

# ------------------------------------------------------------------ dominio

GENEROS = {"m", "f"}

ESPECIALIDADES = {
    "contabil": "Contábil",
    "medica": "Médica",
    "engenharia": "Engenharia",
    "outra": "Outra",
}

# Regionais da Justica do Trabalho. So' TRT por enquanto: o `eh_trabalhista`
# do montar.py exige digito 13 == "5", entao qualquer outro ramo seria
# descartado adiante de qualquer forma.
TRIBUNAIS = {"TRT%d" % n: n for n in range(1, 25)}

_RE_NOME = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'\- ]{4,120}$")


def _limpo(s, tamanho=120):
    return re.sub(r"\s+", " ", (s or "").strip())[:tamanho]


# ------------------------------------------------------------------- tabela

SQL_TABELA = """
create table if not exists pericia_perito (
    id             serial primary key,
    user_id        integer not null unique references "user"(id) on delete cascade,
    nome_tribunal  text    not null,
    variacoes      text    not null default '[]',
    genero         char(1) not null default 'm',
    especialidade  text    not null default 'contabil',
    tribunais      text    not null default '[]',
    token_pje      text,
    configurado_em timestamptz,
    criado_em      timestamptz not null default now(),
    atualizado_em  timestamptz not null default now()
)
"""


def _garantir_tabela(db):
    db.session.execute(text(SQL_TABELA))
    db.session.commit()


# ------------------------------------------------------------------ registro

def register_pericias_routes(app):
    from auth_service import User, db

    # A tabela nasce na PRIMEIRA REQUISICAO, nao no import.
    #
    # No import ainda nao existe contexto de aplicacao do Flask, e o
    # db.session.execute levanta "Working outside of application context". O
    # try/except do auth_service engolia esse erro, as rotas nunca eram
    # registradas e o endpoint respondia 404 — sem nenhum sinal de que algo
    # tinha falhado. Dentro da requisicao o contexto existe.
    #
    # De quebra: banco indisponivel no boot deixa de impedir o registro das
    # rotas. A primeira chamada tenta de novo.
    _pronta = {"tabela": False}

    def _tabela():
        if not _pronta["tabela"]:
            _garantir_tabela(db)
            _pronta["tabela"] = True

    def _atual():
        """Usuario do JWT. A identidade pode ser e-mail ou id."""
        ident = get_jwt_identity()
        if ident is None:
            return None
        u = User.query.filter_by(email=str(ident)).first()
        if u:
            return u
        try:
            return User.query.get(int(ident))
        except (TypeError, ValueError):
            return None

    def _admin():
        """(usuario, erro). Enquanto o modulo esta' em testes, so' admin."""
        _tabela()
        u = _atual()
        if not u:
            return None, (jsonify({"msg": "Sessão inválida."}), 401)
        if (u.role or "") != "admin":
            return None, (jsonify({"msg": "Módulo em testes: acesso restrito."}), 403)
        return u, None

    def _ler(user_id):
        linha = db.session.execute(
            text("select nome_tribunal, variacoes, genero, especialidade, tribunais,"
                 " token_pje, configurado_em"
                 " from pericia_perito where user_id = :u"),
            {"u": user_id},
        ).first()
        if not linha:
            return {"configurado": False}
        return {
            "configurado": linha.configurado_em is not None,
            "nome_tribunal": linha.nome_tribunal,
            "variacoes": json.loads(linha.variacoes or "[]"),
            "genero": linha.genero,
            "especialidade": linha.especialidade,
            "tribunais": json.loads(linha.tribunais or "[]"),
            "tem_token": bool(linha.token_pje),
            "configurado_em": linha.configurado_em.isoformat() if linha.configurado_em else None,
        }

    # ---------------------------------------------------------------- rotas

    @app.route("/api/pericias/perito", methods=["GET"])
    @jwt_required()
    def pericias_perito_ler():
        u, erro = _admin()
        if erro:
            return erro
        return jsonify(_ler(u.id)), 200

    @app.route("/api/pericias/perito", methods=["PUT"])
    @jwt_required()
    def pericias_perito_gravar():
        u, erro = _admin()
        if erro:
            return erro

        d = request.get_json(silent=True) or {}

        nome = _limpo(d.get("nome_tribunal"))
        if not _RE_NOME.match(nome or ""):
            return jsonify({"msg": "Informe o nome completo como o tribunal escreve."}), 400

        variacoes = [_limpo(v) for v in (d.get("variacoes") or []) if _limpo(v)]
        variacoes = [v for v in variacoes if _RE_NOME.match(v)][:5]

        genero = (d.get("genero") or "m").lower()
        if genero not in GENEROS:
            return jsonify({"msg": "Gênero inválido."}), 400

        especialidade = (d.get("especialidade") or "contabil").lower()
        if especialidade not in ESPECIALIDADES:
            return jsonify({"msg": "Especialidade inválida."}), 400

        tribunais = [t.upper() for t in (d.get("tribunais") or []) if t]
        tribunais = sorted({t for t in tribunais if t in TRIBUNAIS}, key=lambda t: TRIBUNAIS[t])
        if not tribunais:
            return jsonify({"msg": "Escolha pelo menos um tribunal."}), 400

        agora = datetime.now(timezone.utc)
        db.session.execute(
            text("""
                insert into pericia_perito
                    (user_id, nome_tribunal, variacoes, genero, especialidade,
                     tribunais, configurado_em, atualizado_em)
                values
                    (:u, :n, :v, :g, :e, :t, :c, :c)
                on conflict (user_id) do update set
                    nome_tribunal = excluded.nome_tribunal,
                    variacoes     = excluded.variacoes,
                    genero        = excluded.genero,
                    especialidade = excluded.especialidade,
                    tribunais     = excluded.tribunais,
                    configurado_em = coalesce(pericia_perito.configurado_em, excluded.configurado_em),
                    atualizado_em  = excluded.atualizado_em
            """),
            {"u": u.id, "n": nome, "v": json.dumps(variacoes, ensure_ascii=False),
             "g": genero, "e": especialidade,
             "t": json.dumps(tribunais), "c": agora},
        )
        db.session.commit()
        return jsonify(_ler(u.id)), 200

    @app.route("/api/pericias/perito/token", methods=["POST"])
    @jwt_required()
    def pericias_perito_token():
        """Sorteia um token novo. Sortear de novo invalida o anterior — e' isso
        que 'revogar' quer dizer aqui. Devolve o valor UMA vez: depois disso
        so' se sabe que existe."""
        u, erro = _admin()
        if erro:
            return erro

        existe = db.session.execute(
            text("select 1 from pericia_perito where user_id = :u"), {"u": u.id}
        ).first()
        if not existe:
            return jsonify({"msg": "Faça o cadastro antes de gerar o token."}), 400

        token = secrets.token_urlsafe(24)
        db.session.execute(
            text("update pericia_perito set token_pje = :t, atualizado_em = now()"
                 " where user_id = :u"),
            {"t": token, "u": u.id},
        )
        db.session.commit()
        return jsonify({"token": token}), 200
