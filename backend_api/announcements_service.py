# /opt/pontua/AutoPonto/backend_api/announcements_service.py
"""
Sistema de Avisos — Sistema Ponto v13.3.0

Avisos bloqueantes que aparecem após login. Independente de promoções e
indicações.

Lógica:
  - 4 tipos: info, warning, critical, news
  - 2 frequências: once (1x por usuário) ou every_session (todo login)
  - every_session só permitido para warning e critical
  - Tracking de acks por usuário (e por sessão JTI quando aplicável)
  - Admin gerencia via aba dedicada em /admin

Convenção: o módulo NÃO cria o `app`; ele recebe referências do auth_service.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

VALID_SEVERITIES = {"info", "warning", "critical", "news"}
VALID_FREQUENCIES = {"once", "every_session"}

# Apenas esses tipos podem ser every_session (segue prática Slack/GitHub)
ALLOWS_EVERY_SESSION = {"warning", "critical"}

# Ranking de severidade para ordenação (menor = aparece primeiro)
SEVERITY_RANK = {
    "critical": 0,
    "warning": 1,
    "info": 2,
    "news": 3,
}


# ═══════════════════════════════════════════════════════════════════════════
# REFERÊNCIAS GLOBAIS (preenchidas por init_announcements_routes)
# ═══════════════════════════════════════════════════════════════════════════

_app = None
_db = None
_User = None
_Announcement = None
_AnnouncementAck = None


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

def _parse_iso(value):
    """Converte string ISO para datetime (aceita 'Z' e timezone-aware)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            from datetime import timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _compute_status(a) -> str:
    """live | scheduled | expired | inactive"""
    if not a.active:
        return "inactive"
    now = datetime.utcnow()
    if a.starts_at and now < a.starts_at:
        return "scheduled"
    if a.ends_at and now > a.ends_at:
        return "expired"
    return "live"


def _validate_severity_frequency(severity: str, frequency: str) -> tuple[bool, str]:
    """Valida combinação de severidade e frequência."""
    if severity not in VALID_SEVERITIES:
        return False, f"Tipo inválido. Use: {', '.join(sorted(VALID_SEVERITIES))}"
    if frequency not in VALID_FREQUENCIES:
        return False, f"Frequência inválida. Use: {', '.join(sorted(VALID_FREQUENCIES))}"
    if frequency == "every_session" and severity not in ALLOWS_EVERY_SESSION:
        return False, (
            f"Frequência 'every_session' só permitida para tipos: "
            f"{', '.join(sorted(ALLOWS_EVERY_SESSION))}. "
            f"Tipos info e news devem ser 'once'."
        )
    return True, ""


def _announcement_to_dict(a, include_stats: bool = False) -> dict[str, Any]:
    data = {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "severity": a.severity,
        "frequency": a.frequency,
        "priority": a.priority,
        "active": a.active,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "status": _compute_status(a),
    }

    if include_stats:
        # Total de usuários elegíveis (todos os ativos)
        total_users = _User.query.filter_by(is_active=True).count()

        # Total de acks únicos (por usuário, ignorando múltiplas sessões)
        unique_acks = _db.session.query(
            func.count(func.distinct(_AnnouncementAck.user_id))
        ).filter(
            _AnnouncementAck.announcement_id == a.id
        ).scalar() or 0

        data["total_users"] = total_users
        data["unique_acks"] = unique_acks
        data["pending_count"] = max(0, total_users - unique_acks)
        data["ack_rate_pct"] = round(
            (unique_acks / total_users * 100), 1
        ) if total_users > 0 else 0.0

    return data


def _hash_jwt_for_session(jwt_payload: dict) -> str:
    """Extrai um identificador estável da sessão a partir do JWT."""
    # Usamos o JTI se existir, senão um hash do iat+sub
    jti = jwt_payload.get("jti")
    if jti:
        return jti[:64]
    # Fallback: jwt issued-at + subject
    iat = jwt_payload.get("iat", 0)
    sub = jwt_payload.get("sub", "")
    return f"{iat}_{sub}"[:64]


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DO USUÁRIO
# ═══════════════════════════════════════════════════════════════════════════

def register_user_endpoints(app):

    @app.route('/api/announcements/pending', methods=['GET'])
    @jwt_required()
    def list_pending_announcements():
        """
        Lista avisos que o usuário ainda precisa ver.

        Filtros:
          - active = True
          - dentro da janela [starts_at, ends_at]
          - se 'once': sem ack do user
          - se 'every_session': sem ack do user nesta sessão (JTI)

        Ordenação: severity asc (crítico primeiro), priority asc, created_at desc.
        """
        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()
        if not user:
            return jsonify({"msg": "Usuário não encontrado"}), 404

        jwt_payload = get_jwt()
        session_id = _hash_jwt_for_session(jwt_payload)

        now = datetime.utcnow()

        # 1. Pega todos os avisos potencialmente válidos
        query = _Announcement.query.filter(_Announcement.active == True)  # noqa: E712
        query = query.filter(
            (_Announcement.starts_at == None) | (_Announcement.starts_at <= now)  # noqa: E711
        )
        query = query.filter(
            (_Announcement.ends_at == None) | (_Announcement.ends_at >= now)  # noqa: E711
        )

        all_eligible = query.all()

        # 2. Para cada um, verifica se o user precisa ver
        pending = []
        for a in all_eligible:
            if a.frequency == "once":
                # Tem ack desse user (qualquer sessão)?
                has_ack = _AnnouncementAck.query.filter_by(
                    announcement_id=a.id,
                    user_id=user.id,
                ).first() is not None
                if has_ack:
                    continue
            else:  # every_session
                # Tem ack nessa sessão específica?
                has_ack_this_session = _AnnouncementAck.query.filter_by(
                    announcement_id=a.id,
                    user_id=user.id,
                    session_id=session_id,
                ).first() is not None
                if has_ack_this_session:
                    continue

            pending.append(a)

        # 3. Ordena por severidade, prioridade, data
        pending.sort(key=lambda a: (
            SEVERITY_RANK.get(a.severity, 99),
            a.priority,
            -(a.created_at.timestamp() if a.created_at else 0),
        ))

        items = [{
            "id": a.id,
            "title": a.title,
            "message": a.message,
            "severity": a.severity,
            "frequency": a.frequency,
        } for a in pending]

        return jsonify({"announcements": items}), 200

    @app.route('/api/announcements/<int:announcement_id>/acknowledge', methods=['POST'])
    @jwt_required()
    def acknowledge_announcement(announcement_id):
        """Marca um aviso como visto pelo usuário."""
        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()
        if not user:
            return jsonify({"msg": "Usuário não encontrado"}), 404

        announcement = _Announcement.query.get(announcement_id)
        if not announcement:
            return jsonify({"msg": "Aviso não encontrado"}), 404

        jwt_payload = get_jwt()
        session_id = _hash_jwt_for_session(jwt_payload)

        # Para 'once': salva sem session_id (constraint única vai prevenir duplicata)
        # Para 'every_session': salva com session_id
        save_session = (
            session_id if announcement.frequency == "every_session" else None
        )

        # Tenta criar — se já existe (once duplicado), ignora silenciosamente
        try:
            ack = _AnnouncementAck(
                announcement_id=announcement_id,
                user_id=user.id,
                session_id=save_session,
                acknowledged_at=datetime.utcnow(),
            )
            _db.session.add(ack)
            _db.session.commit()
            return jsonify({"msg": "ok"}), 200
        except Exception as e:
            _db.session.rollback()
            # Se for IntegrityError de duplicata (once já confirmado), ok
            err_str = str(e).lower()
            if "uq_ack_once" in err_str or "duplicate" in err_str or "unique" in err_str:
                return jsonify({"msg": "already acknowledged"}), 200
            print(f"[ANNOUNCE] Erro ao registrar ack: {e}")
            return jsonify({"msg": "Erro ao registrar confirmação."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE ADMINISTRAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def register_admin_endpoints(app):

    @app.route('/api/admin/announcements', methods=['GET'])
    @_admin_required()
    def admin_list_announcements():
        """Lista todos os avisos com filtro opcional por status computado."""
        status_filter = request.args.get('status', 'all').strip()

        all_items = _Announcement.query.order_by(
            _Announcement.priority.asc(), _Announcement.created_at.desc()
        ).all()

        items = [_announcement_to_dict(a, include_stats=True) for a in all_items]

        if status_filter and status_filter != 'all':
            items = [i for i in items if i['status'] == status_filter]

        stats = {
            'total': len(all_items),
            'live': sum(1 for a in all_items if _compute_status(a) == 'live'),
            'scheduled': sum(1 for a in all_items if _compute_status(a) == 'scheduled'),
            'expired': sum(1 for a in all_items if _compute_status(a) == 'expired'),
            'inactive': sum(1 for a in all_items if _compute_status(a) == 'inactive'),
        }

        return jsonify({
            "items": items,
            "stats": stats,
            "valid_severities": sorted(VALID_SEVERITIES),
            "valid_frequencies": sorted(VALID_FREQUENCIES),
            "allows_every_session": sorted(ALLOWS_EVERY_SESSION),
        }), 200

    @app.route('/api/admin/announcements/<int:announcement_id>', methods=['GET'])
    @_admin_required()
    def admin_get_announcement(announcement_id):
        """Detalhes de um aviso específico."""
        a = _Announcement.query.get(announcement_id)
        if not a:
            return jsonify({"msg": "Aviso não encontrado"}), 404
        return jsonify(_announcement_to_dict(a, include_stats=True)), 200

    @app.route('/api/admin/announcements/<int:announcement_id>/acks', methods=['GET'])
    @_admin_required()
    def admin_list_acks(announcement_id):
        """
        Lista quem confirmou e quem ainda não.
        Query params:
          - view: 'confirmed' | 'pending' | 'all' (default 'all')
          - search: filtra por email
          - page, per_page
        """
        a = _Announcement.query.get(announcement_id)
        if not a:
            return jsonify({"msg": "Aviso não encontrado"}), 404

        view = request.args.get('view', 'all')
        search = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        # Pega últimos acks por usuário (caso tenha vários every_session)
        confirmed_acks = _db.session.query(
            _AnnouncementAck.user_id,
            func.max(_AnnouncementAck.acknowledged_at).label('last_ack'),
            func.count(_AnnouncementAck.id).label('ack_count'),
        ).filter(
            _AnnouncementAck.announcement_id == announcement_id
        ).group_by(_AnnouncementAck.user_id).all()

        confirmed_map = {row.user_id: row for row in confirmed_acks}
        confirmed_ids = set(confirmed_map.keys())

        # Filtro: todos os usuários ativos
        users_query = _User.query.filter_by(is_active=True)
        if search:
            users_query = users_query.filter(_User.email.ilike(f"%{search}%"))

        all_users = users_query.order_by(_User.email).all()

        items = []
        for u in all_users:
            is_confirmed = u.id in confirmed_ids
            if view == 'confirmed' and not is_confirmed:
                continue
            if view == 'pending' and is_confirmed:
                continue

            ack_data = confirmed_map.get(u.id)
            items.append({
                'user_id': u.id,
                'email': u.email,
                'plan_status': u.plan_status,
                'confirmed': is_confirmed,
                'last_ack_at': ack_data.last_ack.isoformat() if ack_data and ack_data.last_ack else None,
                'ack_count': ack_data.ack_count if ack_data else 0,
            })

        total = len(items)
        start = (page - 1) * per_page
        items_page = items[start:start + per_page]

        return jsonify({
            "items": items_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
            "summary": {
                "confirmed": len(confirmed_ids),
                "pending": len(all_users) - len(confirmed_ids),
                "total_users": len(all_users),
            },
        }), 200

    @app.route('/api/admin/announcements', methods=['POST'])
    @_admin_required()
    def admin_create_announcement():
        data = request.get_json() or {}

        title = (data.get('title') or '').strip()
        message = (data.get('message') or '').strip()
        if not title or not message:
            return jsonify({"msg": "Título e mensagem são obrigatórios."}), 400

        severity = data.get('severity', 'info')
        frequency = data.get('frequency', 'once')
        ok, err = _validate_severity_frequency(severity, frequency)
        if not ok:
            return jsonify({"msg": err}), 400

        admin_email = get_jwt_identity()

        a = _Announcement(
            title=title[:200],
            message=message,
            severity=severity,
            frequency=frequency,
            priority=int(data.get('priority', 100)),
            active=bool(data.get('active', True)),
            starts_at=_parse_iso(data.get('starts_at')),
            ends_at=_parse_iso(data.get('ends_at')),
            created_by_admin=admin_email,
        )

        try:
            _db.session.add(a)
            _db.session.commit()
            print(f"[ANNOUNCE] Criado: id={a.id}, severity={a.severity}, "
                  f"freq={a.frequency}, por {admin_email}")
            return jsonify({
                "msg": "Aviso criado.",
                "announcement": _announcement_to_dict(a, include_stats=True),
            }), 201
        except Exception as e:
            _db.session.rollback()
            print(f"[ANNOUNCE] Erro ao criar: {e}")
            return jsonify({"msg": "Erro interno ao criar aviso."}), 500

    @app.route('/api/admin/announcements/<int:announcement_id>', methods=['PUT'])
    @_admin_required()
    def admin_update_announcement(announcement_id):
        a = _Announcement.query.get(announcement_id)
        if not a:
            return jsonify({"msg": "Aviso não encontrado"}), 404

        data = request.get_json() or {}

        if 'title' in data:
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({"msg": "Título não pode ser vazio."}), 400
            a.title = title[:200]

        if 'message' in data:
            message = (data.get('message') or '').strip()
            if not message:
                return jsonify({"msg": "Mensagem não pode ser vazia."}), 400
            a.message = message

        # Severity ou frequency: precisam ser validados juntos
        new_severity = data.get('severity', a.severity)
        new_frequency = data.get('frequency', a.frequency)
        if 'severity' in data or 'frequency' in data:
            ok, err = _validate_severity_frequency(new_severity, new_frequency)
            if not ok:
                return jsonify({"msg": err}), 400
            a.severity = new_severity
            a.frequency = new_frequency

        if 'priority' in data:
            try:
                a.priority = int(data['priority'])
            except (ValueError, TypeError):
                return jsonify({"msg": "Prioridade inválida."}), 400

        if 'active' in data:
            a.active = bool(data['active'])

        if 'starts_at' in data:
            a.starts_at = _parse_iso(data.get('starts_at'))
        if 'ends_at' in data:
            a.ends_at = _parse_iso(data.get('ends_at'))

        a.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            print(f"[ANNOUNCE] Atualizado: id={a.id}")
            return jsonify({
                "msg": "Aviso atualizado.",
                "announcement": _announcement_to_dict(a, include_stats=True),
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[ANNOUNCE] Erro ao atualizar: {e}")
            return jsonify({"msg": "Erro interno ao atualizar aviso."}), 500

    @app.route('/api/admin/announcements/<int:announcement_id>/toggle', methods=['PATCH'])
    @_admin_required()
    def admin_toggle_announcement(announcement_id):
        a = _Announcement.query.get(announcement_id)
        if not a:
            return jsonify({"msg": "Aviso não encontrado"}), 404

        a.active = not a.active
        a.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            state = "ativado" if a.active else "pausado"
            print(f"[ANNOUNCE] {state}: id={a.id}")
            return jsonify({
                "msg": f"Aviso {state}.",
                "active": a.active,
            }), 200
        except Exception as e:
            _db.session.rollback()
            return jsonify({"msg": "Erro ao alternar estado."}), 500

    @app.route('/api/admin/announcements/<int:announcement_id>', methods=['DELETE'])
    @_admin_required()
    def admin_delete_announcement(announcement_id):
        a = _Announcement.query.get(announcement_id)
        if not a:
            return jsonify({"msg": "Aviso não encontrado"}), 404

        try:
            _db.session.delete(a)
            _db.session.commit()
            print(f"[ANNOUNCE] Deletado: id={announcement_id}")
            return jsonify({"msg": "Aviso excluído."}), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[ANNOUNCE] Erro ao deletar: {e}")
            return jsonify({"msg": "Erro ao excluir aviso."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def init_announcements_routes(app, db, User):
    """Registra modelos e endpoints. Chamada do auth_service.py."""
    global _app, _db, _User, _Announcement, _AnnouncementAck
    _app = app
    _db = db
    _User = User

    class Announcement(db.Model):
        __tablename__ = 'announcement'
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(200), nullable=False)
        message = db.Column(db.Text, nullable=False)
        severity = db.Column(db.String(20), nullable=False, default='info', index=True)
        frequency = db.Column(db.String(20), nullable=False, default='once')
        priority = db.Column(db.Integer, nullable=False, default=100)
        active = db.Column(db.Boolean, nullable=False, default=True, index=True)
        starts_at = db.Column(db.DateTime, nullable=True)
        ends_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        created_by_admin = db.Column(db.String(120), nullable=True)

    class AnnouncementAck(db.Model):
        __tablename__ = 'announcement_ack'
        id = db.Column(db.Integer, primary_key=True)
        announcement_id = db.Column(db.Integer,
                                    db.ForeignKey('announcement.id', ondelete='CASCADE'),
                                    nullable=False, index=True)
        user_id = db.Column(db.Integer,
                            db.ForeignKey('user.id', ondelete='CASCADE'),
                            nullable=False, index=True)
        session_id = db.Column(db.String(64), nullable=True, index=True)
        acknowledged_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    _Announcement = Announcement
    _AnnouncementAck = AnnouncementAck

    register_user_endpoints(app)
    register_admin_endpoints(app)

    print("[ANNOUNCE] Módulo de avisos carregado.")
    return Announcement, AnnouncementAck
