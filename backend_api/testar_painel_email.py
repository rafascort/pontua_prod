#!/usr/bin/env python3
"""Testa os endpoints do painel gerando um JWT de admin."""
import json
import urllib.request
from flask_jwt_extended import create_access_token
from auth_service import app, User
import lifecycle_email_service as mailer

BASE = "http://127.0.0.1:5000"


def get(caminho, token=None):
    req = urllib.request.Request(BASE + caminho)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


with app.app_context():
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        print("Nenhum admin encontrado.")
        raise SystemExit(1)
    token = create_access_token(identity=admin.email)

    print("=" * 68)
    print(" TESTE DO PAINEL DE E-MAILS")
    print("=" * 68)

    st, body = get("/api/admin/email-events", token)
    print(f"\n[1] GET /api/admin/email-events  ->  HTTP {st}")
    if st == 200:
        d = json.loads(body)
        print(f"    usuarios: {d['total_usuarios']}  "
              f"e-mails: {d['total_emails']}  falhas: {d['falhas']}")
        for u in d['usuarios']:
            ue = u['ultimo_email']
            marca = f"{ue['rotulo']} ({ue['sent_at'][:16]})" if ue else "—"
            print(f"      {u['email'][:34]:36} {u['segmento']:16} {marca}")
    else:
        print(f"    {body[:200]}")

    alvo = User.query.filter(User.role != 'admin').first()
    st, body = get(f"/api/admin/email-events/{alvo.id}", token)
    print(f"\n[2] GET /api/admin/email-events/{alvo.id}  ->  HTTP {st}")
    if st == 200:
        d = json.loads(body)
        print(f"    {d['usuario']['email']} — {d['total']} evento(s)")
        for h in d['historico']:
            print(f"      {h['sent_at'][:16]}  {h['rotulo']:24} {h['status']}")
    else:
        print(f"    {body[:200]}")

    st, _ = get("/api/admin/email-events")
    print(f"\n[3] Sem token (deve dar 401/422)  ->  HTTP {st}")

    tok = mailer.unsubscribe_token(alvo.id)
    print(f"\n[4] Link de descadastro de {alvo.email}:")
    print(f"    /api/email/unsubscribe?u={alvo.id}&t={tok}")
    st, _ = get(f"/api/email/unsubscribe?u={alvo.id}&t=TOKEN_ERRADO")
    print(f"    Token invalido -> HTTP {st} (deve ser 400)")
    print("\n" + "=" * 68)
    print(" Nao testei o descadastro real para nao marcar ninguem.")
    print(" Para testar: abra o link acima no navegador.")
    print("=" * 68)
