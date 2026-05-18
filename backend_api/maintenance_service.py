# /opt/pontua/AutoPonto/backend_api/maintenance_service.py
"""
Sistema de Modo Manutenção — Sistema Ponto v13.4.1

Gerencia janelas de manutenção programadas e emergenciais.

Funcionalidades:
  - Bloqueio HTTP 503 durante manutenção (via middleware before_request)
  - Whitelist: admin + webhooks Stripe + login + downloads + status público
  - Geração automática de aviso prévio (warning, every_session)
  - Manutenção emergencial com 1 clique
  - Encerramento antecipado e extensão de duração
  - Status `scheduled` → `active` → `completed` (transição automática)

Convenção: o módulo NÃO cria o `app`; ele recebe referências do auth_service.py.

═══════════════════════════════════════════════════════════════════════════
CORREÇÃO v13.4.1 — Bug de horário no frontend
═══════════════════════════════════════════════════════════════════════════
Os datetimes naive (datetime.utcnow()) eram serializados via .isoformat() SEM
o sufixo 'Z', resultando em strings como "2026-05-18T00:36:00". O JavaScript
interpretava essas strings como horário LOCAL e exibia tudo com offset do
fuso (3h adiantado no Brasil/BRT).

Fix: helper `_iso_utc()` adiciona o sufixo 'Z' para marcar explicitamente
como UTC. O frontend (new Date(...).toLocaleString) então converte
corretamente para o fuso local do usuário.

A lógica interna (comparações, queries no banco) continua usando datetime
naive em UTC — só a serialização para o cliente mudou.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional

from flask import jsonify, request, g
from flask_jwt_extended import (
    decode_token, get_jwt, get_jwt_identity, jwt_required,
    verify_jwt_in_request,
)
from sqlalchemy import or_


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

# Status válidos para uma janela de manutenção
VALID_STATUSES = {"scheduled", "active", "completed", "cancelled"}

# Mensagens padrão
DEFAULT_MAINTENANCE_MESSAGE = (
    "Estamos atualizando o sistema para você. Voltamos em breve."
)
DEFAULT_EMERGENCY_MESSAGE = (
    "Sistema temporariamente fora do ar para correção urgente. Voltamos em breve."
)

# ═══════════════════════════════════════════════════════════════════════════
# WHITELIST — rotas que PASSAM mesmo durante manutenção
# ═══════════════════════════════════════════════════════════════════════════

# Rotas exatas (sempre liberadas, mesmo sem auth)
ALWAYS_ALLOWED_PATHS = {
    '/api/login',
    '/api/logout',
    '/api/maintenance/status',           # Status público
    '/api/auth/verify-email',
    '/api/auth/resend-verification',
}

# Prefixos de rotas (qualquer coisa que comece com isso passa)
ALWAYS_ALLOWED_PREFIXES = (
    '/api/webhook/',                      # Webhooks Stripe e outros
    '/api/download/',                     # Downloads de resultados (sua decisão)
)

# Rotas que precisam APENAS de admin (não bloqueiam o admin)
# Todas as rotas /api/admin/* são automaticamente liberadas para admin


# ═══════════════════════════════════════════════════════════════════════════
# REFERÊNCIAS GLOBAIS (preenchidas por init_maintenance_routes)
# ═══════════════════════════════════════════════════════════════════════════

_app = None
_db = None
_User = None
_MaintenanceWindow = None
_Announcement = None  # Referência ao modelo de avisos (para criar aviso prévio)


# ═══════════════════════════════════════════════════════════════════════════
# DECORATOR admin_required
# ═══════════════════════════════════════════════════════════════════════════

def _admin_required():
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') == 'admin':
                return fn(*args, **kwargs)
            return jsonify(msg="Acesso restrito a administradores!"), 403
        return decorator
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Serializa um datetime para ISO 8601 marcando explicitamente como UTC (Z).

    Importante: os datetimes no banco são naive em UTC (gravados via
    datetime.utcnow()). Sem o sufixo 'Z', o JavaScript no frontend interpreta
    essas strings como horário LOCAL, causando offset visual incorreto.

    Esta função:
      - retorna None se dt for None
      - se dt for naive, assume UTC e adiciona 'Z'
      - se dt for aware, converte para UTC e adiciona 'Z'
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    # microsegundos não fazem falta para o cliente — encurta a string
    return dt.replace(microsecond=0).isoformat() + "Z"


def _parse_iso(value):
    """Converte string ISO para datetime naive (UTC)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def get_active_maintenance():
    """Retorna a janela de manutenção ativa AGORA (ou None)."""
    if _MaintenanceWindow is None:
        return None

    now = datetime.utcnow()

    # Marca como completed qualquer ativa que já passou do ends_at
    expired = _MaintenanceWindow.query.filter(
        _MaintenanceWindow.status == 'active',
        _MaintenanceWindow.ends_at < now,
    ).all()
    for m in expired:
        m.status = 'completed'
        m.actually_ended_at = m.actually_ended_at or now
    if expired:
        try:
            _db.session.commit()
        except Exception:
            _db.session.rollback()

    # Promove qualquer scheduled cuja janela já começou
    to_activate = _MaintenanceWindow.query.filter(
        _MaintenanceWindow.status == 'scheduled',
        _MaintenanceWindow.starts_at <= now,
        _MaintenanceWindow.ends_at > now,
    ).all()
    for m in to_activate:
        m.status = 'active'
    if to_activate:
        try:
            _db.session.commit()
            print(f"[MAINT] Manutenção(ões) ativada(s) automaticamente: "
                  f"{[m.id for m in to_activate]}")
        except Exception:
            _db.session.rollback()

    # Retorna a ativa (deve haver no máximo uma de cada vez na prática)
    return _MaintenanceWindow.query.filter_by(status='active').first()


def _maintenance_to_dict(m, include_announcement: bool = False) -> dict[str, Any]:
    data = {
        "id": m.id,
        "announcement_id": m.announcement_id,
        "starts_at": _iso_utc(m.starts_at),
        "ends_at": _iso_utc(m.ends_at),
        "actually_ended_at": _iso_utc(m.actually_ended_at),
        "message": m.message,
        "status": m.status,
        "is_emergency": m.is_emergency,
        "created_at": _iso_utc(m.created_at),
        "updated_at": _iso_utc(m.updated_at),
        "created_by_admin": m.created_by_admin,
    }

    if include_announcement and m.announcement_id and _Announcement is not None:
        ann = _Announcement.query.get(m.announcement_id)
        if ann:
            data["announcement"] = {
                "id": ann.id,
                "title": ann.title,
                "active": ann.active,
                "starts_at": _iso_utc(ann.starts_at),
                "ends_at": _iso_utc(ann.ends_at),
            }

    return data


def _format_pt_br_datetime(dt: datetime) -> str:
    """27/04/2026 02:00"""
    return dt.strftime("%d/%m/%Y %H:%M")


def _create_announcement_for_maintenance(
    starts_at: datetime,
    ends_at: datetime,
    notice_starts_at: datetime,
    custom_title: Optional[str] = None,
    custom_message: Optional[str] = None,
    admin_email: Optional[str] = None,
) -> Optional[int]:
    """
    Cria um aviso prévio (warning, every_session) vinculado a uma manutenção.
    Retorna o ID do aviso criado ou None se falhar.
    """
    if _Announcement is None:
        print("[MAINT] Modelo Announcement não disponível — pulando aviso prévio")
        return None

    # Título e mensagem padrão (admin pode editar depois)
    title = custom_title or (
        f"Manutenção programada — "
        f"{_format_pt_br_datetime(starts_at)} às "
        f"{ends_at.strftime('%H:%M')}"
    )
    message = custom_message or (
        f"O sistema ficará indisponível para atualizações em "
        f"{_format_pt_br_datetime(starts_at)} até "
        f"{_format_pt_br_datetime(ends_at)}.\n\n"
        f"Recomendamos finalizar processamentos em andamento "
        f"antes do início da manutenção."
    )

    try:
        ann = _Announcement(
            title=title[:200],
            message=message,
            severity='warning',
            frequency='every_session',
            priority=10,  # alta prioridade
            active=True,
            starts_at=notice_starts_at,
            ends_at=starts_at,  # aviso para de aparecer quando manutenção começa
            created_by_admin=admin_email or 'system',
        )
        _db.session.add(ann)
        _db.session.commit()
        print(f"[MAINT] Aviso prévio criado: id={ann.id}")
        return ann.id
    except Exception as e:
        _db.session.rollback()
        print(f"[MAINT] Erro ao criar aviso prévio: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE — bloqueia requisições durante manutenção
# ═══════════════════════════════════════════════════════════════════════════

def _is_path_whitelisted(path: str) -> bool:
    """Verifica se o path está na whitelist."""
    if path in ALWAYS_ALLOWED_PATHS:
        return True
    for prefix in ALWAYS_ALLOWED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_admin_request() -> bool:
    """
    Tenta extrair claims do JWT sem falhar se não tiver token.
    Retorna True se for admin.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    try:
        token = auth_header.split(' ', 1)[1]
        decoded = decode_token(token)
        return decoded.get('role') == 'admin'
    except Exception:
        return False


def maintenance_middleware():
    """
    Roda antes de TODA requisição. Decide se bloqueia ou não.

    Regras (em ordem):
      1. Path na whitelist → passa
      2. Admin (JWT válido com role=admin) → passa, mas seta header X-Maintenance-Active
      3. Manutenção ativa → 503
      4. Sem manutenção → passa
    """
    path = request.path

    # 1. Whitelist
    if _is_path_whitelisted(path):
        return None

    # 2. Verifica se é admin (passa sempre, mas com header)
    is_admin = _is_admin_request()

    # 3. Verifica manutenção ativa
    active = get_active_maintenance()

    # Sem manutenção → passa
    if not active:
        return None

    # Admin passa mesmo com manutenção ativa
    if is_admin:
        # Marca em g pra response middleware adicionar header (ou frontend pode
        # consultar /api/maintenance/status pra detectar)
        g.maintenance_active_for_admin = True
        return None

    # Usuário comum → bloqueia
    response = jsonify({
        'maintenance': True,
        'starts_at': _iso_utc(active.starts_at),
        'ends_at': _iso_utc(active.ends_at),
        'message': active.message,
        'msg': 'Sistema em manutenção.',
    })
    response.status_code = 503
    response.headers['Retry-After'] = '30'
    return response


def maintenance_after_request(response):
    """Adiciona header X-Maintenance-Active=true para admin durante manutenção."""
    if getattr(g, 'maintenance_active_for_admin', False):
        response.headers['X-Maintenance-Active'] = 'true'
    return response


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT PÚBLICO — status (sem auth)
# ═══════════════════════════════════════════════════════════════════════════

def register_public_endpoints(app):

    @app.route('/api/maintenance/status', methods=['GET'])
    def maintenance_status():
        """Retorna status atual da manutenção (público, sem auth)."""
        active = get_active_maintenance()

        if active:
            return jsonify({
                'active': True,
                'starts_at': _iso_utc(active.starts_at),
                'ends_at': _iso_utc(active.ends_at),
                'message': active.message,
                'is_emergency': active.is_emergency,
            }), 200

        # Verifica se há manutenção agendada num futuro próximo (até 1h)
        if _MaintenanceWindow is not None:
            now = datetime.utcnow()
            soon = now + timedelta(hours=1)
            upcoming = _MaintenanceWindow.query.filter(
                _MaintenanceWindow.status == 'scheduled',
                _MaintenanceWindow.starts_at > now,
                _MaintenanceWindow.starts_at <= soon,
            ).order_by(_MaintenanceWindow.starts_at.asc()).first()

            if upcoming:
                return jsonify({
                    'active': False,
                    'upcoming': True,
                    'starts_at': _iso_utc(upcoming.starts_at),
                    'ends_at': _iso_utc(upcoming.ends_at),
                    'message': upcoming.message,
                }), 200

        return jsonify({'active': False}), 200


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE ADMINISTRAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def register_admin_endpoints(app):

    @app.route('/api/admin/maintenance', methods=['GET'])
    @_admin_required()
    def admin_list_maintenance():
        """Lista todas as manutenções (passadas, atuais, futuras)."""
        status_filter = request.args.get('status', 'all')

        # Trigger transition checks
        get_active_maintenance()

        query = _MaintenanceWindow.query
        if status_filter and status_filter != 'all':
            query = query.filter_by(status=status_filter)

        items = query.order_by(_MaintenanceWindow.starts_at.desc()).all()
        items_dict = [_maintenance_to_dict(m, include_announcement=True) for m in items]

        # Stats
        all_items = _MaintenanceWindow.query.all()
        stats = {
            'total': len(all_items),
            'active': sum(1 for m in all_items if m.status == 'active'),
            'scheduled': sum(1 for m in all_items if m.status == 'scheduled'),
            'completed': sum(1 for m in all_items if m.status == 'completed'),
            'cancelled': sum(1 for m in all_items if m.status == 'cancelled'),
        }

        return jsonify({
            "items": items_dict,
            "stats": stats,
        }), 200

    @app.route('/api/admin/maintenance/active', methods=['GET'])
    @_admin_required()
    def admin_get_active():
        """Detalhes da manutenção ativa agora."""
        active = get_active_maintenance()
        if not active:
            return jsonify({"active": False}), 200

        # Calcula tempo decorrido e restante
        now = datetime.utcnow()
        elapsed_seconds = max(0, int((now - active.starts_at).total_seconds()))
        remaining_seconds = max(0, int((active.ends_at - now).total_seconds()))

        data = _maintenance_to_dict(active, include_announcement=True)
        data["active"] = True
        data["elapsed_seconds"] = elapsed_seconds
        data["remaining_seconds"] = remaining_seconds

        return jsonify(data), 200

    @app.route('/api/admin/maintenance', methods=['POST'])
    @_admin_required()
    def admin_create_maintenance():
        """Cria uma janela de manutenção programada."""
        data = request.get_json() or {}

        starts_at = _parse_iso(data.get('starts_at'))
        ends_at = _parse_iso(data.get('ends_at'))

        if not starts_at or not ends_at:
            return jsonify({"msg": "Início e fim são obrigatórios."}), 400

        if ends_at <= starts_at:
            return jsonify({"msg": "Fim deve ser após o início."}), 400

        now = datetime.utcnow()
        if starts_at < now - timedelta(minutes=5):
            return jsonify({
                "msg": "Início não pode ser no passado. Use manutenção emergencial para iniciar agora."
            }), 400

        message = (data.get('message') or '').strip() or DEFAULT_MAINTENANCE_MESSAGE
        admin_email = get_jwt_identity()

        # Verifica sobreposição com outras janelas (warning, não bloqueia)
        overlap = _MaintenanceWindow.query.filter(
            _MaintenanceWindow.status.in_(['scheduled', 'active']),
            _MaintenanceWindow.starts_at < ends_at,
            _MaintenanceWindow.ends_at > starts_at,
        ).first()

        warning_overlap = None
        if overlap:
            warning_overlap = (
                f"Já existe outra manutenção programada na mesma janela "
                f"(id={overlap.id}, {_format_pt_br_datetime(overlap.starts_at)} → "
                f"{_format_pt_br_datetime(overlap.ends_at)}). Continue se intencional."
            )

        # Cria aviso prévio (se admin pediu)
        create_announcement = data.get('create_announcement', True)
        announcement_id = None

        if create_announcement:
            # Aviso começa X horas antes (default: 48h ou no momento da criação,
            # o que for mais cedo)
            notice_hours_before = int(data.get('notice_hours_before', 48))
            notice_starts_at = max(
                now,  # nunca no passado
                starts_at - timedelta(hours=notice_hours_before),
            )

            announcement_id = _create_announcement_for_maintenance(
                starts_at=starts_at,
                ends_at=ends_at,
                notice_starts_at=notice_starts_at,
                custom_title=data.get('announcement_title'),
                custom_message=data.get('announcement_message'),
                admin_email=admin_email,
            )

        # Cria a manutenção
        try:
            m = _MaintenanceWindow(
                announcement_id=announcement_id,
                starts_at=starts_at,
                ends_at=ends_at,
                message=message,
                status='scheduled',
                is_emergency=False,
                created_by_admin=admin_email,
            )
            _db.session.add(m)
            _db.session.commit()
            print(f"[MAINT] Programada: id={m.id}, "
                  f"{_format_pt_br_datetime(starts_at)} → "
                  f"{_format_pt_br_datetime(ends_at)}, "
                  f"por {admin_email}")

            response = {
                "msg": "Manutenção programada.",
                "maintenance": _maintenance_to_dict(m, include_announcement=True),
            }
            if warning_overlap:
                response["warning"] = warning_overlap

            return jsonify(response), 201
        except Exception as e:
            _db.session.rollback()
            print(f"[MAINT] Erro ao criar manutenção: {e}")
            return jsonify({"msg": "Erro interno ao criar manutenção."}), 500

    @app.route('/api/admin/maintenance/emergency', methods=['POST'])
    @_admin_required()
    def admin_create_emergency():
        """Ativa manutenção emergencial AGORA."""
        data = request.get_json() or {}

        # Default: 1h de duração
        duration_minutes = int(data.get('duration_minutes', 60))
        if duration_minutes < 5 or duration_minutes > 24 * 60:
            return jsonify({"msg": "Duração deve estar entre 5 minutos e 24 horas."}), 400

        now = datetime.utcnow()
        starts_at = now
        ends_at = now + timedelta(minutes=duration_minutes)

        message = (data.get('message') or '').strip() or DEFAULT_EMERGENCY_MESSAGE
        admin_email = get_jwt_identity()

        try:
            m = _MaintenanceWindow(
                announcement_id=None,
                starts_at=starts_at,
                ends_at=ends_at,
                message=message,
                status='active',  # já entra ativa
                is_emergency=True,
                created_by_admin=admin_email,
            )
            _db.session.add(m)
            _db.session.commit()
            print(f"[MAINT] ⚠ EMERGENCIAL ativada: id={m.id}, "
                  f"duração={duration_minutes}min, por {admin_email}")

            return jsonify({
                "msg": "Manutenção emergencial ativada.",
                "maintenance": _maintenance_to_dict(m),
            }), 201
        except Exception as e:
            _db.session.rollback()
            print(f"[MAINT] Erro ao criar emergencial: {e}")
            return jsonify({"msg": "Erro interno."}), 500

    @app.route('/api/admin/maintenance/<int:maint_id>', methods=['PATCH'])
    @_admin_required()
    def admin_update_maintenance(maint_id):
        """Edita uma manutenção (mensagem, ends_at, etc)."""
        m = _MaintenanceWindow.query.get(maint_id)
        if not m:
            return jsonify({"msg": "Manutenção não encontrada."}), 404

        if m.status in ('completed', 'cancelled'):
            return jsonify({"msg": "Não é possível editar manutenção encerrada."}), 400

        data = request.get_json() or {}

        if 'message' in data:
            new_msg = (data.get('message') or '').strip()
            if new_msg:
                m.message = new_msg

        if 'ends_at' in data:
            new_end = _parse_iso(data.get('ends_at'))
            if new_end and new_end > datetime.utcnow():
                m.ends_at = new_end

        if 'starts_at' in data and m.status == 'scheduled':
            new_start = _parse_iso(data.get('starts_at'))
            if new_start and new_start > datetime.utcnow():
                m.starts_at = new_start

        m.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            print(f"[MAINT] Atualizada: id={m.id}")
            return jsonify({
                "msg": "Manutenção atualizada.",
                "maintenance": _maintenance_to_dict(m, include_announcement=True),
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[MAINT] Erro ao atualizar: {e}")
            return jsonify({"msg": "Erro interno."}), 500

    @app.route('/api/admin/maintenance/<int:maint_id>/end', methods=['PATCH'])
    @_admin_required()
    def admin_end_maintenance(maint_id):
        """Encerra manutenção antes do previsto."""
        m = _MaintenanceWindow.query.get(maint_id)
        if not m:
            return jsonify({"msg": "Manutenção não encontrada."}), 404

        if m.status != 'active':
            return jsonify({"msg": "Apenas manutenções ativas podem ser encerradas."}), 400

        now = datetime.utcnow()
        m.status = 'completed'
        m.actually_ended_at = now
        m.updated_at = now

        try:
            _db.session.commit()
            print(f"[MAINT] Encerrada antes do previsto: id={m.id}")
            return jsonify({
                "msg": "Manutenção encerrada.",
                "maintenance": _maintenance_to_dict(m),
            }), 200
        except Exception as e:
            _db.session.rollback()
            return jsonify({"msg": "Erro interno."}), 500

    @app.route('/api/admin/maintenance/<int:maint_id>/extend', methods=['PATCH'])
    @_admin_required()
    def admin_extend_maintenance(maint_id):
        """Estende a manutenção com mais minutos a partir de agora."""
        m = _MaintenanceWindow.query.get(maint_id)
        if not m:
            return jsonify({"msg": "Manutenção não encontrada."}), 404

        if m.status != 'active':
            return jsonify({"msg": "Apenas manutenções ativas podem ser estendidas."}), 400

        data = request.get_json() or {}
        extra_minutes = int(data.get('extra_minutes', 30))
        if extra_minutes < 5 or extra_minutes > 24 * 60:
            return jsonify({"msg": "Adicione entre 5 minutos e 24 horas."}), 400

        new_end = m.ends_at + timedelta(minutes=extra_minutes)
        m.ends_at = new_end
        m.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            print(f"[MAINT] Estendida: id={m.id}, +{extra_minutes}min, "
                  f"novo fim: {_format_pt_br_datetime(new_end)}")
            return jsonify({
                "msg": f"Manutenção estendida por {extra_minutes} minutos.",
                "maintenance": _maintenance_to_dict(m),
            }), 200
        except Exception as e:
            _db.session.rollback()
            return jsonify({"msg": "Erro interno."}), 500

    @app.route('/api/admin/maintenance/<int:maint_id>', methods=['DELETE'])
    @_admin_required()
    def admin_delete_maintenance(maint_id):
        """Exclui uma manutenção (apenas se status=scheduled)."""
        m = _MaintenanceWindow.query.get(maint_id)
        if not m:
            return jsonify({"msg": "Manutenção não encontrada."}), 404

        if m.status != 'scheduled':
            return jsonify({
                "msg": "Apenas manutenções agendadas podem ser excluídas. "
                       "Use 'encerrar' para parar uma ativa."
            }), 400

        # Se tinha aviso prévio vinculado, desativa
        if m.announcement_id and _Announcement is not None:
            ann = _Announcement.query.get(m.announcement_id)
            if ann:
                ann.active = False
                ann.updated_at = datetime.utcnow()

        try:
            _db.session.delete(m)
            _db.session.commit()
            print(f"[MAINT] Excluída: id={maint_id}")
            return jsonify({"msg": "Manutenção excluída."}), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[MAINT] Erro ao excluir: {e}")
            return jsonify({"msg": "Erro interno."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def init_maintenance_routes(app, db, User, Announcement=None):
    """Registra modelo, middleware e endpoints. Chamada do auth_service.py."""
    global _app, _db, _User, _MaintenanceWindow, _Announcement
    _app = app
    _db = db
    _User = User
    _Announcement = Announcement

    class MaintenanceWindow(db.Model):
        __tablename__ = 'maintenance_window'
        id = db.Column(db.Integer, primary_key=True)
        announcement_id = db.Column(db.Integer,
                                    db.ForeignKey('announcement.id', ondelete='SET NULL'),
                                    nullable=True)
        starts_at = db.Column(db.DateTime, nullable=False, index=True)
        ends_at = db.Column(db.DateTime, nullable=False, index=True)
        actually_ended_at = db.Column(db.DateTime, nullable=True)
        message = db.Column(db.Text, nullable=False)
        status = db.Column(db.String(20), nullable=False,
                           default='scheduled', index=True)
        is_emergency = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        created_by_admin = db.Column(db.String(120), nullable=True)

    _MaintenanceWindow = MaintenanceWindow

    # Registra middleware de bloqueio
    app.before_request(maintenance_middleware)
    app.after_request(maintenance_after_request)

    register_public_endpoints(app)
    register_admin_endpoints(app)

    print("[MAINT] Módulo de manutenção carregado.")
    return MaintenanceWindow
