# /opt/pontua/AutoPonto/backend_api/promotions_service.py
"""
Sistema de Promoções Dinâmicas — Sistema Ponto v13.2.0

CRUD de campanhas promocionais gerenciadas pelo admin. Informativas (não
aplicam desconto sozinhas — desconto real é configurado no Stripe como
Promotion Code, e a promoção apenas exibe o código para o usuário copiar).

Convenção: o módulo NÃO cria o `app`; ele recebe referências do auth_service.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

VALID_CTA_TYPES = {"none", "contact", "link", "code"}

VALID_COLORS = {
    "emerald", "indigo", "amber", "rose",
    "blue", "violet", "teal", "slate",
}

VALID_ICONS = {
    "Sparkles", "Gift", "Zap", "Star", "Trophy", "Tag", "Percent",
    "Rocket", "Flame", "Heart", "Crown", "PartyPopper", "Megaphone",
    "Calendar", "TrendingUp", "Award", "ShieldCheck",
}

VALID_EVENT_TYPES = {"impression", "cta_click"}


# ═══════════════════════════════════════════════════════════════════════════
# REFERÊNCIAS GLOBAIS (preenchidas por init_promotions_routes)
# ═══════════════════════════════════════════════════════════════════════════

_app = None
_db = None
_User = None
_Promotion = None
_PromotionMetric = None


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
    """Converte string ISO para datetime (aceita Z e timezone-aware/naive)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Suporte para 'Z' (UTC) — Python 3.10 não aceita direto
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        # Normaliza para naive (igual ao que o Postgres grava)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _compute_status(promo) -> str:
    """Calcula status dinâmico: live | scheduled | expired | inactive."""
    if not promo.active:
        return "inactive"
    now = datetime.utcnow()
    if promo.starts_at and now < promo.starts_at:
        return "scheduled"
    if promo.ends_at and now > promo.ends_at:
        return "expired"
    return "live"


def _validate_cta(cta_type: str, cta_value) -> tuple[bool, str]:
    """Valida consistência CTA type ↔ value."""
    if cta_type not in VALID_CTA_TYPES:
        return False, f"Tipo de CTA inválido. Use um de: {', '.join(sorted(VALID_CTA_TYPES))}"

    if cta_type in ("link", "code") and not (cta_value and str(cta_value).strip()):
        return False, f"CTA do tipo '{cta_type}' requer um valor."

    if cta_type == "link":
        val = str(cta_value).strip()
        if not (val.startswith("http://") or val.startswith("https://") or val.startswith("/")):
            return False, "CTA tipo 'link' deve começar com http(s):// ou /"

    return True, ""


def _promotion_to_dict(p, include_stats: bool = False) -> dict[str, Any]:
    """Serializa uma Promotion para JSON."""
    data = {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "badge_label": p.badge_label,
        "badge_color": p.badge_color,
        "icon": p.icon,
        "discount_hint": p.discount_hint,
        "cta_type": p.cta_type,
        "cta_value": p.cta_value,
        "cta_label": p.cta_label,
        "priority": p.priority,
        "active": p.active,
        "starts_at": p.starts_at.isoformat() if p.starts_at else None,
        "ends_at": p.ends_at.isoformat() if p.ends_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "status": _compute_status(p),
    }

    if include_stats:
        impressions = _PromotionMetric.query.filter_by(
            promotion_id=p.id, event_type='impression'
        ).count()
        clicks = _PromotionMetric.query.filter_by(
            promotion_id=p.id, event_type='cta_click'
        ).count()
        data["impressions"] = impressions
        data["clicks"] = clicks
        data["click_rate"] = round((clicks / impressions * 100), 1) if impressions > 0 else 0.0

    return data


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DO USUÁRIO
# ═══════════════════════════════════════════════════════════════════════════

def register_user_endpoints(app):

    @app.route('/api/promotions/active', methods=['GET'])
    @jwt_required()
    def list_active_promotions():
        """Lista promoções ativas (active + dentro do período)."""
        now = datetime.utcnow()

        query = _Promotion.query.filter(_Promotion.active == True)  # noqa: E712
        query = query.filter(
            (_Promotion.starts_at == None) | (_Promotion.starts_at <= now)  # noqa: E711
        )
        query = query.filter(
            (_Promotion.ends_at == None) | (_Promotion.ends_at >= now)  # noqa: E711
        )
        query = query.order_by(_Promotion.priority.asc(), _Promotion.created_at.desc())

        promos = query.all()
        return jsonify({
            "promotions": [_promotion_to_dict(p) for p in promos],
        }), 200

    @app.route('/api/promotions/<int:promotion_id>/track', methods=['POST'])
    @jwt_required()
    def track_promotion_event(promotion_id):
        """Registra uma impressão ou clique em CTA."""
        data = request.get_json() or {}
        event_type = data.get('event_type', '').strip()

        if event_type not in VALID_EVENT_TYPES:
            return jsonify({"msg": "event_type inválido."}), 400

        promo = _Promotion.query.get(promotion_id)
        if not promo:
            return jsonify({"msg": "Promoção não encontrada."}), 404

        current_email = get_jwt_identity()
        user = _User.query.filter_by(email=current_email).first()

        try:
            metric = _PromotionMetric(
                promotion_id=promotion_id,
                user_id=user.id if user else None,
                event_type=event_type,
                created_at=datetime.utcnow(),
            )
            _db.session.add(metric)
            _db.session.commit()
            return jsonify({"msg": "ok"}), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[PROMO] Erro ao registrar métrica: {e}")
            return jsonify({"msg": "Erro ao registrar métrica."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE ADMINISTRAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def register_admin_endpoints(app):

    @app.route('/api/admin/promotions', methods=['GET'])
    @_admin_required()
    def admin_list_promotions():
        """
        Lista todas as promoções com filtro opcional por status computado.
        ?status=live|scheduled|expired|inactive|all
        """
        status_filter = request.args.get('status', 'all').strip()

        all_promos = _Promotion.query.order_by(
            _Promotion.priority.asc(), _Promotion.created_at.desc()
        ).all()

        items = [_promotion_to_dict(p, include_stats=True) for p in all_promos]

        if status_filter and status_filter != 'all':
            items = [i for i in items if i['status'] == status_filter]

        # Estatísticas agregadas
        stats = {
            'total': len(all_promos),
            'live': sum(1 for p in all_promos if _compute_status(p) == 'live'),
            'scheduled': sum(1 for p in all_promos if _compute_status(p) == 'scheduled'),
            'expired': sum(1 for p in all_promos if _compute_status(p) == 'expired'),
            'inactive': sum(1 for p in all_promos if _compute_status(p) == 'inactive'),
        }

        return jsonify({
            "items": items,
            "stats": stats,
            "valid_cta_types": sorted(VALID_CTA_TYPES),
            "valid_colors": sorted(VALID_COLORS),
            "valid_icons": sorted(VALID_ICONS),
        }), 200

    @app.route('/api/admin/promotions/<int:promotion_id>', methods=['GET'])
    @_admin_required()
    def admin_get_promotion(promotion_id):
        """Detalhes de uma promoção + métricas diárias dos últimos 60 dias."""
        promo = _Promotion.query.get(promotion_id)
        if not promo:
            return jsonify({"msg": "Promoção não encontrada."}), 404

        data = _promotion_to_dict(promo, include_stats=True)

        # Métricas agrupadas por dia (últimos 60 dias)
        since = datetime.utcnow() - timedelta(days=60)

        daily_rows = _db.session.query(
            func.date(_PromotionMetric.created_at).label('day'),
            _PromotionMetric.event_type,
            func.count(_PromotionMetric.id).label('count'),
        ).filter(
            _PromotionMetric.promotion_id == promotion_id,
            _PromotionMetric.created_at >= since,
        ).group_by(
            func.date(_PromotionMetric.created_at),
            _PromotionMetric.event_type,
        ).all()

        daily: dict[str, dict[str, int]] = {}
        for row in daily_rows:
            day_str = row.day.isoformat() if row.day else ''
            if day_str not in daily:
                daily[day_str] = {'impression': 0, 'cta_click': 0}
            daily[day_str][row.event_type] = row.count

        data['daily_metrics'] = [
            {
                'date': day,
                'impressions': m.get('impression', 0),
                'clicks': m.get('cta_click', 0),
            }
            for day, m in sorted(daily.items())
        ]
        return jsonify(data), 200

    @app.route('/api/admin/promotions', methods=['POST'])
    @_admin_required()
    def admin_create_promotion():
        data = request.get_json() or {}

        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()
        if not title or not description:
            return jsonify({"msg": "Título e descrição são obrigatórios."}), 400

        badge_color = data.get('badge_color', 'emerald')
        if badge_color not in VALID_COLORS:
            return jsonify({"msg": f"Cor inválida. Use: {', '.join(sorted(VALID_COLORS))}"}), 400

        icon = data.get('icon', 'Sparkles')
        if icon not in VALID_ICONS:
            return jsonify({"msg": f"Ícone inválido."}), 400

        cta_type = data.get('cta_type', 'none')
        cta_value = data.get('cta_value')
        ok, err = _validate_cta(cta_type, cta_value)
        if not ok:
            return jsonify({"msg": err}), 400

        admin_email = get_jwt_identity()

        promo = _Promotion(
            title=title[:200],
            description=description,
            badge_label=(data.get('badge_label') or 'Promoção')[:50],
            badge_color=badge_color,
            icon=icon,
            discount_hint=(data.get('discount_hint') or None),
            cta_type=cta_type,
            cta_value=(str(cta_value).strip() if cta_value else None),
            cta_label=(data.get('cta_label') or None),
            priority=int(data.get('priority', 100)),
            active=bool(data.get('active', True)),
            starts_at=_parse_iso(data.get('starts_at')),
            ends_at=_parse_iso(data.get('ends_at')),
            created_by_admin=admin_email,
        )

        try:
            _db.session.add(promo)
            _db.session.commit()
            print(f"[PROMO] Criada: id={promo.id}, título='{promo.title}', por {admin_email}")
            return jsonify({
                "msg": "Promoção criada.",
                "promotion": _promotion_to_dict(promo, include_stats=True),
            }), 201
        except Exception as e:
            _db.session.rollback()
            print(f"[PROMO] Erro ao criar: {e}")
            return jsonify({"msg": "Erro interno ao criar promoção."}), 500

    @app.route('/api/admin/promotions/<int:promotion_id>', methods=['PUT'])
    @_admin_required()
    def admin_update_promotion(promotion_id):
        promo = _Promotion.query.get(promotion_id)
        if not promo:
            return jsonify({"msg": "Promoção não encontrada."}), 404

        data = request.get_json() or {}

        if 'title' in data:
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({"msg": "Título não pode ser vazio."}), 400
            promo.title = title[:200]

        if 'description' in data:
            description = (data.get('description') or '').strip()
            if not description:
                return jsonify({"msg": "Descrição não pode ser vazia."}), 400
            promo.description = description

        if 'badge_label' in data:
            promo.badge_label = (data.get('badge_label') or 'Promoção')[:50]

        if 'badge_color' in data:
            if data['badge_color'] not in VALID_COLORS:
                return jsonify({"msg": "Cor inválida."}), 400
            promo.badge_color = data['badge_color']

        if 'icon' in data:
            if data['icon'] not in VALID_ICONS:
                return jsonify({"msg": "Ícone inválido."}), 400
            promo.icon = data['icon']

        if 'discount_hint' in data:
            promo.discount_hint = data.get('discount_hint') or None

        if 'cta_type' in data or 'cta_value' in data:
            new_cta_type = data.get('cta_type', promo.cta_type)
            new_cta_value = data.get('cta_value', promo.cta_value)
            ok, err = _validate_cta(new_cta_type, new_cta_value)
            if not ok:
                return jsonify({"msg": err}), 400
            promo.cta_type = new_cta_type
            promo.cta_value = (str(new_cta_value).strip() if new_cta_value else None)

        if 'cta_label' in data:
            promo.cta_label = data.get('cta_label') or None

        if 'priority' in data:
            try:
                promo.priority = int(data['priority'])
            except (ValueError, TypeError):
                return jsonify({"msg": "Prioridade inválida."}), 400

        if 'active' in data:
            promo.active = bool(data['active'])

        if 'starts_at' in data:
            promo.starts_at = _parse_iso(data.get('starts_at'))

        if 'ends_at' in data:
            promo.ends_at = _parse_iso(data.get('ends_at'))

        promo.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            print(f"[PROMO] Atualizada: id={promo.id}")
            return jsonify({
                "msg": "Promoção atualizada.",
                "promotion": _promotion_to_dict(promo, include_stats=True),
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[PROMO] Erro ao atualizar: {e}")
            return jsonify({"msg": "Erro interno ao atualizar promoção."}), 500

    @app.route('/api/admin/promotions/<int:promotion_id>/toggle', methods=['PATCH'])
    @_admin_required()
    def admin_toggle_promotion(promotion_id):
        """Alterna o campo active rapidamente."""
        promo = _Promotion.query.get(promotion_id)
        if not promo:
            return jsonify({"msg": "Promoção não encontrada."}), 404

        promo.active = not promo.active
        promo.updated_at = datetime.utcnow()

        try:
            _db.session.commit()
            state = "ativada" if promo.active else "pausada"
            print(f"[PROMO] {state}: id={promo.id}")
            return jsonify({
                "msg": f"Promoção {state}.",
                "active": promo.active,
            }), 200
        except Exception as e:
            _db.session.rollback()
            return jsonify({"msg": "Erro ao alternar estado."}), 500

    @app.route('/api/admin/promotions/<int:promotion_id>', methods=['DELETE'])
    @_admin_required()
    def admin_delete_promotion(promotion_id):
        promo = _Promotion.query.get(promotion_id)
        if not promo:
            return jsonify({"msg": "Promoção não encontrada."}), 404

        try:
            _db.session.delete(promo)
            _db.session.commit()
            print(f"[PROMO] Deletada: id={promotion_id}")
            return jsonify({"msg": "Promoção excluída."}), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[PROMO] Erro ao deletar: {e}")
            return jsonify({"msg": "Erro ao excluir promoção."}), 500


# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def init_promotions_routes(app, db, User):
    """Registra modelos e endpoints. Chamada do auth_service.py."""
    global _app, _db, _User, _Promotion, _PromotionMetric
    _app = app
    _db = db
    _User = User

    class Promotion(db.Model):
        __tablename__ = 'promotion'
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(200), nullable=False)
        description = db.Column(db.Text, nullable=False)
        badge_label = db.Column(db.String(50), nullable=False, default='Promoção')
        badge_color = db.Column(db.String(20), nullable=False, default='emerald')
        icon = db.Column(db.String(50), nullable=False, default='Sparkles')
        discount_hint = db.Column(db.String(60), nullable=True)
        cta_type = db.Column(db.String(20), nullable=False, default='none')
        cta_value = db.Column(db.String(500), nullable=True)
        cta_label = db.Column(db.String(80), nullable=True)
        priority = db.Column(db.Integer, nullable=False, default=100, index=True)
        active = db.Column(db.Boolean, nullable=False, default=True, index=True)
        starts_at = db.Column(db.DateTime, nullable=True)
        ends_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        created_by_admin = db.Column(db.String(120), nullable=True)

    class PromotionMetric(db.Model):
        __tablename__ = 'promotion_metric'
        id = db.Column(db.Integer, primary_key=True)
        promotion_id = db.Column(db.Integer,
                                 db.ForeignKey('promotion.id', ondelete='CASCADE'),
                                 nullable=False, index=True)
        user_id = db.Column(db.Integer,
                            db.ForeignKey('user.id', ondelete='SET NULL'),
                            nullable=True)
        event_type = db.Column(db.String(20), nullable=False, index=True)
        created_at = db.Column(db.DateTime, nullable=False,
                               default=datetime.utcnow, index=True)

    _Promotion = Promotion
    _PromotionMetric = PromotionMetric

    register_user_endpoints(app)
    register_admin_endpoints(app)

    print("[PROMO] Módulo de promoções carregado.")
    return Promotion, PromotionMetric
