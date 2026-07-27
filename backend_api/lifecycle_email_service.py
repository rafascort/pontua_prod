# /opt/pontua/AutoPonto/backend_api/lifecycle_email_service.py
"""
Envio dos e-mails do ciclo de vida — Sistema Ponto

Toda saida passa por send(). Ele garante, sempre:
  1. respeita opt-out (LGPD)
  2. nunca envia o mesmo tipo duas vezes para a mesma pessoa
  3. registra em email_event (fonte do painel admin)

Nada dispara sozinho: este modulo so envia quando alguem chama.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import smtplib
import ssl
import traceback
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import email_templates

FRONTEND = os.getenv('FRONTEND_URL', 'https://sistemaponto.com')

# Tipos que podem repetir (a idempotencia usa a chave em meta['ciclo'])
REPETIVEIS = {'reminder', 'renewal', 'idle_subscriber', 'high_usage', 'payment_failed'}


def _lazy():
    from auth_service import app, db, User, EmailEvent
    return app, db, User, EmailEvent


# ── Descadastro ───────────────────────────────────────────────────────

def _segredo() -> str:
    return (os.getenv('JWT_SECRET_KEY') or os.getenv('SECRET_KEY')
            or 'pontua-fallback-secret')


def unsubscribe_token(user_id: int) -> str:
    return hmac.new(_segredo().encode(), f"unsub:{user_id}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def verify_unsubscribe_token(user_id: int, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(user_id), (token or '').strip())


def unsubscribe_url(user_id: int) -> str:
    return f"{FRONTEND}/api/email/unsubscribe?u={user_id}&t={unsubscribe_token(user_id)}"


# ── SMTP ──────────────────────────────────────────────────────────────

def _smtp_send(to_email: str, assunto: str, html: str, texto: str) -> tuple[bool, str]:
    host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "contato@sistemaponto.com")
    senha = os.getenv("SMTP_PASSWORD")
    nome = os.getenv("SMTP_FROM_NAME", "Sistema Ponto")

    if not senha:
        return False, "SMTP_PASSWORD nao configurado no .env"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = f"{nome} <{user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
            s.login(user, senha)
            s.send_message(msg)
        return True, "ok"
    except Exception as e:
        return False, str(e)


# ── Historico ─────────────────────────────────────────────────────────

def already_sent(user_id: int, tipo: str, ciclo: Optional[str] = None) -> bool:
    _, _, _, EmailEvent = _lazy()
    q = EmailEvent.query.filter_by(user_id=user_id, email_type=tipo, status='sent')
    if ciclo is None:
        return q.first() is not None
    for ev in q.all():
        try:
            if (json.loads(ev.meta or '{}') or {}).get('ciclo') == ciclo:
                return True
        except Exception:
            continue
    return False


def record(user_id: int, tipo: str, status: str, meta: Optional[dict] = None):
    _, db, _, EmailEvent = _lazy()
    ev = EmailEvent(user_id=user_id, email_type=tipo, status=status,
                    sent_at=datetime.now(timezone.utc),
                    meta=json.dumps(meta or {}, ensure_ascii=False))
    db.session.add(ev)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[EMAIL] Falha ao registrar evento: {e}")
    return ev


def last_email(user_id: int):
    _, _, _, EmailEvent = _lazy()
    return (EmailEvent.query.filter_by(user_id=user_id)
            .order_by(EmailEvent.sent_at.desc()).first())


# ── Entrada principal ─────────────────────────────────────────────────

def send(user, tipo: str, contexto: Optional[dict] = None,
         ciclo: Optional[str] = None, force: bool = False,
         dry_run: bool = False) -> bool:
    """
    Envia um e-mail do ciclo de vida.

    ciclo   -> chave para tipos repetiveis (ex: '2026-07' na renovacao)
    force   -> ignora a checagem de duplicidade (uso manual)
    dry_run -> renderiza e valida, mas nao envia nem registra
    """
    contexto = contexto or {}

    if getattr(user, 'email_opt_out', False):
        print(f"[EMAIL] {user.email} pediu para nao receber. Ignorado ({tipo}).")
        return False
    if not user.email:
        return False

    if not force and already_sent(user.id, tipo, ciclo):
        print(f"[EMAIL] {tipo} ja enviado para {user.email}. Ignorado.")
        return False

    try:
        assunto, html, texto = email_templates.render(
            tipo, user, contexto, unsubscribe_url(user.id))
    except Exception as e:
        print(f"[EMAIL] Erro ao renderizar '{tipo}' para {user.email}: {e}")
        traceback.print_exc()
        return False

    if dry_run:
        print(f"[EMAIL][DRY] {tipo} -> {user.email} | {assunto}")
        return True

    ok, detalhe = _smtp_send(user.email, assunto, html, texto)
    meta = dict(contexto)
    if ciclo:
        meta['ciclo'] = ciclo
    meta['assunto'] = assunto
    if not ok:
        meta['erro'] = detalhe[:400]

    record(user.id, tipo, 'sent' if ok else 'failed', meta)
    print(f"[EMAIL] {'OK  ' if ok else 'FALHA'} {tipo} -> {user.email}"
          + ('' if ok else f' | {detalhe}'))
    return ok


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    app, db, User, EmailEvent = _lazy()

    args = sys.argv[1:]
    if not args:
        print("Uso:")
        print("  python lifecycle_email_service.py listar")
        print("  python lifecycle_email_service.py previa <tipo>")
        print("  python lifecycle_email_service.py enviar <tipo> <email>")
        sys.exit(0)

    cmd = args[0]

    if cmd == "listar":
        print("Tipos disponiveis:")
        for t in sorted(email_templates.TEMPLATES):
            print(f"  {t}")
        sys.exit(0)

    with app.app_context():
        if cmd == "previa":
            tipo = args[1]
            u = User.query.filter(User.role != 'admin').first()
            ctx = {'codigo': 'BV10ABC123', 'validade': '28/07/2026',
                   'pct_mes_1': 20, 'pct_mes_2_3': 10, 'dias_restantes': 12,
                   'usadas_anterior': 189, 'variante': 0}
            assunto, html, _ = email_templates.render(
                tipo, u, ctx, unsubscribe_url(u.id))
            caminho = f"/tmp/previa_{tipo}.html"
            open(caminho, "w", encoding="utf-8").write(html)
            print(f"Assunto: {assunto}")
            print(f"HTML salvo em: {caminho}")
            print(f"Baixe com:  scp root@SEU_IP:{caminho} .")

        elif cmd == "enviar":
            tipo, destino = args[1], args[2]
            u = User.query.filter_by(email=destino).first()
            if not u:
                print(f"Usuario {destino} nao encontrado no banco.")
                sys.exit(1)
            ctx = {'codigo': 'BV10TESTE', 'validade': '28/07/2026',
                   'pct_mes_1': 20, 'pct_mes_2_3': 10, 'dias_restantes': 12,
                   'usadas_anterior': 189, 'variante': 0}
            ok = send(u, tipo, ctx, force=True)
            print("Enviado." if ok else "Falhou — veja o erro acima.")
        else:
            print(f"Comando desconhecido: {cmd}")
