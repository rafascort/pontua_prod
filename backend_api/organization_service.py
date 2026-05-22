# backend_api/organization_service.py
"""
Multi-tenancy / Empresas — endpoints administrativos.

Modulo carregado pelo auth_service.py via init_organization_routes().

Endpoints expostos (somente admin do sistema):
  GET    /api/admin/organizations
  POST   /api/admin/organizations
  GET    /api/admin/organizations/<id>
  PATCH  /api/admin/organizations/<id>
  PATCH  /api/admin/organizations/<id>/status
  POST   /api/admin/organizations/<id>/members
  PATCH  /api/admin/organizations/<id>/members/<uid>
  DELETE /api/admin/organizations/<id>/members/<uid>
"""

import os
import re
import secrets
import traceback
from datetime import datetime, timezone

from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from sqlalchemy import or_


# ─── Module-level singletons (preenchidas por init) ────────────────────
_app = None
_db = None
_User = None
_Organization = None

# Planos pagos avulsos que bloqueiam migracao para empresa
PAID_PLANS_BLOCKING = ('basic', 'standard', 'premium', 'past_due')


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _validate_email(email):
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def _normalize_cnpj(cnpj):
    """Remove tudo que nao for digito. Retorna None se vazio."""
    if not cnpj:
        return None
    cleaned = re.sub(r'\D', '', str(cnpj))
    return cleaned if cleaned else None


def _generate_invite_token():
    return secrets.token_urlsafe(48)


def _build_invite_link(token):
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    return f"{frontend_url}/definir-senha?token={token}"


def _user_summary(u):
    """Dicionario com dados do usuario, usado em respostas."""
    return {
        'id': u.id,
        'email': u.email,
        'is_active': bool(u.is_active),
        'org_role': u.org_role,
        'can_process': bool(u.can_process) if u.can_process is not None else True,
        'page_count': u.page_count or 0,
        'plan_status_legacy': u.plan_status,  # info historica (usuario avulso)
    }


# ═══════════════════════════════════════════════════════════════════════
# REGISTRO DOS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

def _register_endpoints(app, admin_required):

    # ─── 1. Listar empresas ─────────────────────────────────────────────
    @app.route('/api/admin/organizations', methods=['GET'])
    @admin_required()
    def admin_list_organizations():
        try:
            page = max(1, int(request.args.get('page', 1)))
            per_page = min(100, max(1, int(request.args.get('per_page', 25))))
            search = (request.args.get('search') or '').strip()
            status_filter = (request.args.get('plan_status') or '').strip()

            query = _Organization.query

            if search:
                like = f"%{search}%"
                cnpj_digits = _normalize_cnpj(search)
                conds = [
                    _Organization.name.ilike(like),
                    _Organization.billing_email.ilike(like),
                    _Organization.cnpj.ilike(like),
                ]
                if cnpj_digits:
                    conds.append(_Organization.cnpj.ilike(f"%{cnpj_digits}%"))
                query = query.filter(or_(*conds))

            if status_filter:
                query = query.filter(_Organization.plan_status == status_filter)

            query = query.order_by(_Organization.created_at.desc())
            total = query.count()
            items = query.offset((page - 1) * per_page).limit(per_page).all()

            result = []
            for org in items:
                member_count = _User.query.filter_by(organization_id=org.id).count()
                cents = (org.page_count or 0) * (org.price_per_page_cents or 0)
                result.append({
                    **org.to_dict(),
                    'member_count': member_count,
                    'estimated_invoice_cents': cents,
                    'estimated_invoice_brl': round(cents / 100, 2),
                })

            return jsonify({
                'organizations': result,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page if total else 1,
            }), 200

        except Exception as e:
            print(f"[ORG] Erro list_organizations: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao listar empresas."}), 500


    # ─── 2. Criar empresa ───────────────────────────────────────────────
    @app.route('/api/admin/organizations', methods=['POST'])
    @admin_required()
    def admin_create_organization():
        try:
            data = request.get_json() or {}
            current_admin_email = get_jwt_identity()
            current_admin = _User.query.filter_by(email=current_admin_email).first()

            # ─ Validacao da empresa ─
            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({"msg": "Campo 'name' obrigatorio."}), 400

            billing_email = (data.get('billing_email') or '').strip().lower()
            if not _validate_email(billing_email):
                return jsonify({"msg": "Campo 'billing_email' invalido."}), 400

            cnpj_clean = _normalize_cnpj(data.get('cnpj'))
            if cnpj_clean and len(cnpj_clean) != 14:
                return jsonify({"msg": "CNPJ deve ter 14 digitos."}), 400

            price = data.get('price_per_page_cents', 62)
            try:
                price = int(price)
            except (TypeError, ValueError):
                return jsonify({"msg": "price_per_page_cents deve ser inteiro."}), 400
            if price < 1 or price > 10000:
                return jsonify({"msg": "price_per_page_cents fora do intervalo (1-10000)."}), 400

            # ─ Validacao do admin da empresa ─
            admin_email = (data.get('admin_email') or '').strip().lower()
            if not _validate_email(admin_email):
                return jsonify({"msg": "Campo 'admin_email' invalido."}), 400

            admin_can_process = data.get('admin_can_process', True)
            if not isinstance(admin_can_process, bool):
                admin_can_process = True

            # ─ Unicidade CNPJ ─
            if cnpj_clean:
                exists = _Organization.query.filter_by(cnpj=cnpj_clean).first()
                if exists:
                    return jsonify({
                        "msg": f"Ja existe empresa com este CNPJ (id={exists.id})."
                    }), 409

            # ─ Resolver admin (migrar avulso ou criar novo) ─
            invite_link = None
            migrated = False
            existing = _User.query.filter_by(email=admin_email).first()

            if existing:
                if existing.organization_id:
                    return jsonify({
                        "msg": f"Usuario {admin_email} ja pertence a outra empresa "
                               f"(id={existing.organization_id})."
                    }), 409
                if (existing.plan_status or 'free') in PAID_PLANS_BLOCKING:
                    return jsonify({
                        "msg": f"Usuario {admin_email} possui plano '{existing.plan_status}' "
                               f"ativo no Stripe. Cancele a assinatura no painel do Stripe "
                               f"antes de adiciona-lo a uma empresa."
                    }), 409
                admin_user = existing
                migrated = True
            else:
                admin_user = _User(
                    email=admin_email,
                    role='user',
                    is_active=True,
                    plan_status='free',
                    page_count=0,
                )
                token = _generate_invite_token()
                admin_user.password_reset_token = token
                admin_user.password_reset_sent_at = datetime.now(timezone.utc)
                if hasattr(admin_user, 'email_verified'):
                    admin_user.email_verified = True
                _db.session.add(admin_user)
                _db.session.flush()  # obtem admin_user.id
                invite_link = _build_invite_link(token)

            # ─ Criar organization ─
            org = _Organization(
                name=name,
                legal_name=(data.get('legal_name') or '').strip() or None,
                cnpj=cnpj_clean,
                billing_email=billing_email,
                is_active=True,
                plan_status='awaiting_setup',
                price_per_page_cents=price,
                pending_price_per_page_cents=None,
                page_count=0,
                created_by_admin_id=current_admin.id if current_admin else None,
            )
            _db.session.add(org)
            _db.session.flush()

            # ─ Vincular admin a empresa ─
            admin_user.organization_id = org.id
            admin_user.org_role = 'admin'
            admin_user.can_process = admin_can_process

            _db.session.commit()
            # Envia email de boas-vindas para o admin da empresa (se for novo)
            if invite_link:
                try:
                    send_org_admin_welcome_email(admin_email, org.name, invite_link)
                except Exception as e:
                    print(f"[ORG] Falha ao enviar email de boas-vindas: {e}")


            print(f"[ORG] Empresa #{org.id} '{org.name}' criada por {current_admin_email}. "
                  f"Admin: {admin_email} ({'migrado' if migrated else 'novo'}).")

            return jsonify({
                "msg": "Empresa criada com sucesso.",
                "organization": org.to_dict(),
                "admin_user": _user_summary(admin_user),
                "admin_was_migrated": migrated,
                "invite_link": invite_link,
            }), 201

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro create_organization: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao criar empresa."}), 500


    # ─── 3. Detalhe da empresa ──────────────────────────────────────────
    @app.route('/api/admin/organizations/<int:org_id>', methods=['GET'])
    @admin_required()
    def admin_get_organization(org_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404

        members = _User.query.filter_by(organization_id=org.id).order_by(
            _User.org_role.desc(),  # 'admin' antes de 'member'
            _User.email.asc()
        ).all()

        cents = (org.page_count or 0) * (org.price_per_page_cents or 0)
        return jsonify({
            'organization': org.to_dict(),
            'estimated_invoice_cents': cents,
            'estimated_invoice_brl': round(cents / 100, 2),
            'members': [_user_summary(m) for m in members],
            'member_count': len(members),
        }), 200


    # ─── 4. Editar empresa ──────────────────────────────────────────────
    @app.route('/api/admin/organizations/<int:org_id>', methods=['PATCH'])
    @admin_required()
    def admin_update_organization(org_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404

        try:
            data = request.get_json() or {}
            changes = []

            if 'name' in data:
                new_name = (data['name'] or '').strip()
                if not new_name:
                    return jsonify({"msg": "Nome nao pode ser vazio."}), 400
                org.name = new_name
                changes.append('name')

            if 'legal_name' in data:
                org.legal_name = (data['legal_name'] or '').strip() or None
                changes.append('legal_name')

            if 'cnpj' in data:
                cnpj_clean = _normalize_cnpj(data['cnpj'])
                if cnpj_clean and len(cnpj_clean) != 14:
                    return jsonify({"msg": "CNPJ deve ter 14 digitos."}), 400
                if cnpj_clean and cnpj_clean != org.cnpj:
                    other = _Organization.query.filter_by(cnpj=cnpj_clean).first()
                    if other and other.id != org.id:
                        return jsonify({"msg": "CNPJ ja usado por outra empresa."}), 409
                org.cnpj = cnpj_clean
                changes.append('cnpj')

            if 'billing_email' in data:
                new_email = (data['billing_email'] or '').strip().lower()
                if not _validate_email(new_email):
                    return jsonify({"msg": "billing_email invalido."}), 400
                org.billing_email = new_email
                changes.append('billing_email')

            if 'price_per_page_cents' in data:
                try:
                    new_price = int(data['price_per_page_cents'])
                except (TypeError, ValueError):
                    return jsonify({"msg": "price_per_page_cents invalido."}), 400
                if new_price < 1 or new_price > 10000:
                    return jsonify({"msg": "price_per_page_cents fora do intervalo."}), 400

                if new_price == (org.price_per_page_cents or 0):
                    # mesmo preco vigente -> cancela alteracao pendente
                    org.pending_price_per_page_cents = None
                else:
                    # diferente -> agenda para o proximo ciclo
                    org.pending_price_per_page_cents = new_price
                changes.append('pending_price_per_page_cents')

            if 'next_reset_date' in data:
                if data['next_reset_date']:
                    try:
                        org.next_reset_date = datetime.fromisoformat(
                            data['next_reset_date']
                        ).date()
                    except ValueError:
                        return jsonify({"msg": "next_reset_date deve ser YYYY-MM-DD."}), 400
                else:
                    org.next_reset_date = None
                changes.append('next_reset_date')

            if not changes:
                return jsonify({"msg": "Nenhum campo enviado."}), 400

            org.updated_at = datetime.utcnow()
            _db.session.commit()

            print(f"[ORG] Empresa #{org.id} atualizada. Campos: {changes}")
            return jsonify({
                "msg": "Empresa atualizada.",
                "organization": org.to_dict(),
                "changed_fields": changes,
            }), 200

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro update_organization {org_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao atualizar empresa."}), 500


    # ─── 5. Suspender / reativar empresa ────────────────────────────────
    @app.route('/api/admin/organizations/<int:org_id>/status', methods=['PATCH'])
    @admin_required()
    def admin_set_organization_status(org_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404

        try:
            data = request.get_json() or {}
            action = data.get('action')
            if action not in ('suspend', 'reactivate'):
                return jsonify({"msg": "action deve ser 'suspend' ou 'reactivate'."}), 400

            if action == 'suspend':
                org.is_active = False
                org.plan_status = 'suspended'
                log_msg = "SUSPENSA"
            else:
                org.is_active = True
                org.plan_status = 'active' if org.stripe_subscription_id else 'awaiting_setup'
                log_msg = "REATIVADA"

            org.updated_at = datetime.utcnow()
            _db.session.commit()
            print(f"[ORG] Empresa #{org.id} {log_msg} por admin do sistema.")
            return jsonify({
                "msg": f"Empresa {action}.",
                "organization": org.to_dict(),
            }), 200

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro set_status {org_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao alterar status."}), 500


# ─── 5b. Gerar checkout do Stripe para a empresa ────────────────────
    @app.route('/api/admin/organizations/<int:org_id>/checkout-session',
               methods=['POST'])
    @admin_required()
    def admin_create_org_checkout(org_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404
        if not org.is_active:
            return jsonify({"msg": "Empresa esta inativa."}), 400

        try:
            from stripe_org_service import create_checkout_session_for_org
            url = create_checkout_session_for_org(org)
            return jsonify({
                "msg": "Checkout session criado.",
                "url": url,
                "organization": org.to_dict(),
            }), 200
        except Exception as e:
            print(f"[ORG] Erro checkout empresa {org_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": f"Erro ao gerar checkout: {str(e)}"}), 500

    # ─── 6. Adicionar membro ────────────────────────────────────────────

    @app.route('/api/admin/organizations/<int:org_id>/members', methods=['POST'])
    @admin_required()
    def admin_add_member(org_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404

        try:
            data = request.get_json() or {}
            email = (data.get('email') or '').strip().lower()
            if not _validate_email(email):
                return jsonify({"msg": "Email invalido."}), 400

            role = (data.get('role') or 'member').strip().lower()
            if role not in ('admin', 'member'):
                return jsonify({"msg": "role deve ser 'admin' ou 'member'."}), 400

            can_process_flag = data.get('can_process', True)
            if not isinstance(can_process_flag, bool):
                can_process_flag = True

            existing = _User.query.filter_by(email=email).first()
            invite_link = None
            migrated = False

            if existing:
                if existing.organization_id:
                    if existing.organization_id == org.id:
                        return jsonify({"msg": "Usuario ja e membro desta empresa."}), 409
                    return jsonify({
                        "msg": f"Usuario ja pertence a outra empresa "
                               f"(id={existing.organization_id})."
                    }), 409
                if (existing.plan_status or 'free') in PAID_PLANS_BLOCKING:
                    return jsonify({
                        "msg": f"Usuario {email} possui plano '{existing.plan_status}' "
                               f"ativo no Stripe. Cancele a assinatura antes de migra-lo."
                    }), 409
                user = existing
                migrated = True
            else:
                user = _User(
                    email=email,
                    role='user',
                    is_active=True,
                    plan_status='free',
                    page_count=0,
                )
                token = _generate_invite_token()
                user.password_reset_token = token
                user.password_reset_sent_at = datetime.now(timezone.utc)
                if hasattr(user, 'email_verified'):
                    user.email_verified = True
                _db.session.add(user)
                _db.session.flush()
                invite_link = _build_invite_link(token)

            user.organization_id = org.id
            user.org_role = role
            # membros sempre podem processar; flag so importa para admin
            user.can_process = True if role == 'member' else can_process_flag

            _db.session.commit()

            # Envia email de convite (se for novo usuario)
            if invite_link:
                try:
                    send_org_member_invite_email(email, org.name, invite_link, get_jwt_identity())
                except Exception as e:
                    print(f"[ORG] Falha ao enviar email de convite: {e}")
            print(f"[ORG] Membro {email} adicionado a empresa #{org.id} como {role} "
                  f"({'migrado' if migrated else 'novo'}).")
            return jsonify({
                "msg": "Membro adicionado.",
                "member": _user_summary(user),
                "was_migrated": migrated,
                "invite_link": invite_link,
            }), 201

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro add_member em org {org_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao adicionar membro."}), 500


    # ─── 7. Editar membro ───────────────────────────────────────────────
    @app.route('/api/admin/organizations/<int:org_id>/members/<int:user_id>',
               methods=['PATCH'])
    @admin_required()
    def admin_update_member(org_id, user_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404
        user = _User.query.get(user_id)
        if not user or user.organization_id != org.id:
            return jsonify({"msg": "Membro nao encontrado nesta empresa."}), 404

        try:
            data = request.get_json() or {}
            changes = []

            if 'org_role' in data:
                new_role = (data['org_role'] or '').strip().lower()
                if new_role not in ('admin', 'member'):
                    return jsonify({"msg": "org_role deve ser 'admin' ou 'member'."}), 400
                if user.org_role == 'admin' and new_role == 'member':
                    admin_count = _User.query.filter_by(
                        organization_id=org.id, org_role='admin'
                    ).count()
                    if admin_count <= 1:
                        return jsonify({
                            "msg": "Nao e possivel rebaixar o ultimo admin da empresa."
                        }), 400
                user.org_role = new_role
                if new_role == 'member':
                    user.can_process = True  # membros sempre processam
                changes.append('org_role')

            if 'can_process' in data:
                if not isinstance(data['can_process'], bool):
                    return jsonify({"msg": "can_process deve ser true ou false."}), 400
                # so faz sentido alterar para admin de empresa
                if user.org_role == 'admin':
                    user.can_process = data['can_process']
                    changes.append('can_process')

            if 'is_active' in data:
                if not isinstance(data['is_active'], bool):
                    return jsonify({"msg": "is_active deve ser true ou false."}), 400
                user.is_active = data['is_active']
                changes.append('is_active')

            if not changes:
                return jsonify({"msg": "Nenhum campo enviado."}), 400

            _db.session.commit()
            print(f"[ORG] Membro #{user.id} ({user.email}) atualizado em org #{org.id}. "
                  f"Campos: {changes}")
            return jsonify({
                "msg": "Membro atualizado.",
                "member": _user_summary(user),
                "changed_fields": changes,
            }), 200

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro update_member {user_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao atualizar membro."}), 500


    # ─── 8. Remover membro da empresa ───────────────────────────────────
    @app.route('/api/admin/organizations/<int:org_id>/members/<int:user_id>',
               methods=['DELETE'])
    @admin_required()
    def admin_remove_member(org_id, user_id):
        org = _Organization.query.get(org_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404
        user = _User.query.get(user_id)
        if not user or user.organization_id != org.id:
            return jsonify({"msg": "Membro nao encontrado nesta empresa."}), 404

        try:
            if user.org_role == 'admin':
                admin_count = _User.query.filter_by(
                    organization_id=org.id, org_role='admin'
                ).count()
                if admin_count <= 1:
                    return jsonify({
                        "msg": "Nao e possivel remover o ultimo admin da empresa."
                    }), 400

            email = user.email
            user.organization_id = None
            user.org_role = None
            user.can_process = True
            # usuario continua existindo (vira avulso de novo)
            _db.session.commit()
            print(f"[ORG] Membro {email} desvinculado de org #{org.id}. "
                  f"Voltou a ser usuario avulso.")
            return jsonify({
                "msg": "Membro removido da empresa.",
                "ex_member": _user_summary(user),
            }), 200

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG] Erro remove_member {user_id}: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao remover membro."}), 500


# ═══════════════════════════════════════════════════════════════════════
# INIT — chamada do auth_service.py
# ═══════════════════════════════════════════════════════════════════════

def init_organization_routes(app, db, User, Organization, admin_required, org_admin_required):
    """Registra endpoints. Chamada do auth_service.py."""
    global _app, _db, _User, _Organization
    _app = app
    _db = db
    _User = User
    _Organization = Organization


    _register_endpoints(app, admin_required)
    _register_org_endpoints(app, org_admin_required)
    _register_invite_endpoints(app)

    print("[ORG] Modulo de empresas (multi-tenancy) carregado. "
          "8 endpoints /api/admin/organizations + 9 endpoints /api/org + 2 endpoints /api/org/invite registrados.")
    return Organization
# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS PARA O ADMIN DA EMPRESA (/api/org/*)
# Acessados pela propria Marcia/admin de cada empresa — nao por voce
# ═══════════════════════════════════════════════════════════════════════

def _register_org_endpoints(app, org_admin_required):
    """Endpoints /api/org/* — sempre operam na empresa do JWT."""

    def _get_my_org():
        """Helper: retorna (org, None) ou (None, response_400/404)."""
        claims = get_jwt()
        org_id = claims.get('organization_id')
        if not org_id:
            return None, (jsonify({
                "msg": "Esta rota e exclusiva de administradores de empresa."
            }), 400)
        org = _Organization.query.get(org_id)
        if not org:
            return None, (jsonify({"msg": "Empresa nao encontrada."}), 404)
        return org, None


    # ─── 1. GET /api/org/me ─────────────────────────────────────────────
    @app.route('/api/org/me', methods=['GET'])
    @org_admin_required()
    def org_get_me():
        org, err = _get_my_org()
        if err: return err
        cents = (org.page_count or 0) * (org.price_per_page_cents or 0)
        member_count = _User.query.filter_by(organization_id=org.id).count()
        return jsonify({
            'organization': org.to_dict(),
            'member_count': member_count,
            'estimated_invoice_cents': cents,
            'estimated_invoice_brl': round(cents / 100, 2),
        }), 200


    # ─── 2. PATCH /api/org/me ───────────────────────────────────────────
    @app.route('/api/org/me', methods=['PATCH'])
    @org_admin_required()
    def org_update_me():
        org, err = _get_my_org()
        if err: return err
        try:
            data = request.get_json() or {}
            changes = []

            if 'name' in data:
                new_name = (data['name'] or '').strip()
                if not new_name:
                    return jsonify({"msg": "Nome nao pode ser vazio."}), 400
                org.name = new_name
                changes.append('name')

            if 'billing_email' in data:
                new_email = (data['billing_email'] or '').strip().lower()
                if not _validate_email(new_email):
                    return jsonify({"msg": "billing_email invalido."}), 400
                org.billing_email = new_email
                changes.append('billing_email')

            if not changes:
                return jsonify({"msg": "Nenhum campo enviado."}), 400

            org.updated_at = datetime.utcnow()
            _db.session.commit()
            print(f"[ORG-SELF] Empresa #{org.id} editou: {changes}")
            return jsonify({
                "msg": "Empresa atualizada.",
                "organization": org.to_dict(),
                "changed_fields": changes,
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[ORG-SELF] Erro org_update_me: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao atualizar empresa."}), 500


    # ─── 3. GET /api/org/members ────────────────────────────────────────
    @app.route('/api/org/members', methods=['GET'])
    @org_admin_required()
    def org_list_members():
        org, err = _get_my_org()
        if err: return err
        members = _User.query.filter_by(organization_id=org.id).order_by(
            _User.org_role.desc(),
            _User.email.asc()
        ).all()
        return jsonify({
            'members': [_user_summary(m) for m in members],
            'total': len(members),
        }), 200


    # ─── 4. POST /api/org/members (convidar) ────────────────────────────
    @app.route('/api/org/members', methods=['POST'])
    @org_admin_required()
    def org_invite_member():
        org, err = _get_my_org()
        if err: return err
        try:
            data = request.get_json() or {}
            email = (data.get('email') or '').strip().lower()
            if not _validate_email(email):
                return jsonify({"msg": "Email invalido."}), 400

            role = (data.get('role') or 'member').strip().lower()
            if role not in ('admin', 'member'):
                return jsonify({"msg": "role deve ser 'admin' ou 'member'."}), 400

            can_process_flag = data.get('can_process', True)
            if not isinstance(can_process_flag, bool):
                can_process_flag = True

            existing = _User.query.filter_by(email=email).first()
            invite_link = None
            migrated = False

            if existing:
                if existing.organization_id:
                    if existing.organization_id == org.id:
                        return jsonify({"msg": "Esta pessoa ja e membro da empresa."}), 409
                    return jsonify({
                        "msg": "Este email ja pertence a outra empresa."
                    }), 409
                if (existing.plan_status or 'free') in PAID_PLANS_BLOCKING:
                    return jsonify({
                        "msg": f"Este email possui plano '{existing.plan_status}' "
                               f"ativo. A pessoa precisa cancelar a propria "
                               f"assinatura no Stripe antes de se juntar a empresa."
                    }), 409
                user = existing
                migrated = True
            else:
                user = _User(
                    email=email, role='user', is_active=True,
                    plan_status='free', page_count=0,
                )
                token = _generate_invite_token()
                user.password_reset_token = token
                user.password_reset_sent_at = datetime.now(timezone.utc)
                if hasattr(user, 'email_verified'):
                    user.email_verified = True
                _db.session.add(user)
                _db.session.flush()
                invite_link = _build_invite_link(token)

            user.organization_id = org.id
            user.org_role = role
            user.can_process = True if role == 'member' else can_process_flag
            _db.session.commit()
            # Envia email de convite (se for novo usuario)
            if invite_link:
                try:
                    send_org_member_invite_email(email, org.name, invite_link, get_jwt_identity())
                except Exception as e:
                    print(f"[ORG-SELF] Falha ao enviar email: {e}")
            print(f"[ORG-SELF] Empresa #{org.id} convidou {email} como {role} "
                  f"({'migrado' if migrated else 'novo'}).")
            return jsonify({
                "msg": "Membro adicionado.",
                "member": _user_summary(user),
                "was_migrated": migrated,
                "invite_link": invite_link,
            }), 201
        except Exception as e:
            _db.session.rollback()
            print(f"[ORG-SELF] Erro org_invite_member: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao adicionar membro."}), 500


    # ─── 5. PATCH /api/org/members/<uid> ────────────────────────────────
    @app.route('/api/org/members/<int:user_id>', methods=['PATCH'])
    @org_admin_required()
    def org_update_member(user_id):
        org, err = _get_my_org()
        if err: return err
        user = _User.query.get(user_id)
        if not user or user.organization_id != org.id:
            return jsonify({"msg": "Membro nao encontrado nesta empresa."}), 404

        try:
            data = request.get_json() or {}
            changes = []
            current_email = get_jwt_identity()
            is_self = (user.email == current_email)

            if 'org_role' in data:
                new_role = (data['org_role'] or '').strip().lower()
                if new_role not in ('admin', 'member'):
                    return jsonify({"msg": "org_role deve ser 'admin' ou 'member'."}), 400
                if is_self and new_role != 'admin':
                    return jsonify({"msg": "Voce nao pode se rebaixar."}), 400
                if user.org_role == 'admin' and new_role == 'member':
                    admin_count = _User.query.filter_by(
                        organization_id=org.id, org_role='admin'
                    ).count()
                    if admin_count <= 1:
                        return jsonify({"msg": "Nao e possivel rebaixar o ultimo admin."}), 400
                user.org_role = new_role
                if new_role == 'member':
                    user.can_process = True
                changes.append('org_role')

            if 'can_process' in data:
                if not isinstance(data['can_process'], bool):
                    return jsonify({"msg": "can_process deve ser true ou false."}), 400
                if user.org_role == 'admin':
                    user.can_process = data['can_process']
                    changes.append('can_process')

            if 'is_active' in data:
                if not isinstance(data['is_active'], bool):
                    return jsonify({"msg": "is_active deve ser true ou false."}), 400
                if is_self and not data['is_active']:
                    return jsonify({"msg": "Voce nao pode desativar sua propria conta."}), 400
                user.is_active = data['is_active']
                changes.append('is_active')

            if not changes:
                return jsonify({"msg": "Nenhum campo enviado."}), 400

            _db.session.commit()
            print(f"[ORG-SELF] Empresa #{org.id} editou membro #{user.id}: {changes}")
            return jsonify({
                "msg": "Membro atualizado.",
                "member": _user_summary(user),
                "changed_fields": changes,
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[ORG-SELF] Erro org_update_member: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao atualizar membro."}), 500


    # ─── 6. DELETE /api/org/members/<uid> ───────────────────────────────
    @app.route('/api/org/members/<int:user_id>', methods=['DELETE'])
    @org_admin_required()
    def org_remove_member(user_id):
        org, err = _get_my_org()
        if err: return err
        user = _User.query.get(user_id)
        if not user or user.organization_id != org.id:
            return jsonify({"msg": "Membro nao encontrado nesta empresa."}), 404

        current_email = get_jwt_identity()
        if user.email == current_email:
            return jsonify({"msg": "Voce nao pode remover sua propria conta."}), 400

        try:
            if user.org_role == 'admin':
                admin_count = _User.query.filter_by(
                    organization_id=org.id, org_role='admin'
                ).count()
                if admin_count <= 1:
                    return jsonify({"msg": "Nao e possivel remover o ultimo admin."}), 400

            email = user.email
            user.organization_id = None
            user.org_role = None
            user.can_process = True
            _db.session.commit()
            print(f"[ORG-SELF] Empresa #{org.id} removeu {email}.")
            return jsonify({
                "msg": "Membro removido da empresa.",
                "ex_member": _user_summary(user),
            }), 200
        except Exception as e:
            _db.session.rollback()
            print(f"[ORG-SELF] Erro org_remove_member: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao remover."}), 500


    # ─── 7. POST /api/org/checkout-session ──────────────────────────────
    @app.route('/api/org/checkout-session', methods=['POST'])
    @org_admin_required()
    def org_create_checkout():
        org, err = _get_my_org()
        if err: return err
        if org.plan_status not in ('awaiting_setup', 'past_due', 'inactive'):
            return jsonify({
                "msg": f"Empresa ja esta em status '{org.plan_status}'. "
                       f"Use o portal do Stripe para gerenciar pagamento."
            }), 400
        try:
            from stripe_org_service import create_checkout_session_for_org
            url = create_checkout_session_for_org(org)
            return jsonify({"msg": "Checkout session criado.", "url": url}), 200
        except Exception as e:
            print(f"[ORG-SELF] Erro org_checkout: {e}")
            traceback.print_exc()
            return jsonify({"msg": f"Erro ao gerar checkout: {str(e)}"}), 500


    # ─── 8. POST /api/org/portal-session ────────────────────────────────
    @app.route('/api/org/portal-session', methods=['POST'])
    @org_admin_required()
    def org_create_portal():
        org, err = _get_my_org()
        if err: return err
        if not org.stripe_customer_id:
            return jsonify({
                "msg": "Empresa ainda nao tem cartao cadastrado. "
                       "Use /api/org/checkout-session primeiro."
            }), 400
        try:
            import stripe
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
            portal_session = stripe.billing_portal.Session.create(
                customer=org.stripe_customer_id,
                return_url=f"{frontend_url}/empresa",
            )
            return jsonify({'url': portal_session.url}), 200
        except Exception as e:
            print(f"[ORG-SELF] Erro org_portal: {e}")
            traceback.print_exc()
            return jsonify({"msg": f"Erro portal: {str(e)}"}), 500


    # ─── 9. GET /api/org/invoices ───────────────────────────────────────
    @app.route('/api/org/invoices', methods=['GET'])
    @org_admin_required()
    def org_list_invoices():
        org, err = _get_my_org()
        if err: return err
        if not org.stripe_customer_id:
            return jsonify({'invoices': [], 'total': 0}), 200
        try:
            import stripe
            invoices = stripe.Invoice.list(customer=org.stripe_customer_id, limit=24)
            result = []
            for inv in invoices.data:
                result.append({
                    'id': inv.id,
                    'number': inv.get('number'),
                    'status': inv.get('status'),
                    'amount_due_cents': inv.get('amount_due', 0),
                    'amount_paid_cents': inv.get('amount_paid', 0),
                    'currency': inv.get('currency', 'brl'),
                    'created': inv.get('created'),
                    'period_start': inv.get('period_start'),
                    'period_end': inv.get('period_end'),
                    'hosted_invoice_url': inv.get('hosted_invoice_url'),
                    'invoice_pdf': inv.get('invoice_pdf'),
                })
            return jsonify({'invoices': result, 'total': len(result)}), 200
        except Exception as e:
            print(f"[ORG-SELF] Erro org_invoices: {e}")
            traceback.print_exc()
            return jsonify({"msg": f"Erro: {str(e)}"}), 500
# ═══════════════════════════════════════════════════════════════════════
# ENVIO DE E-MAILS DE ONBOARDING
# Reaproveita SMTP do .env (Hostinger SMTP_SSL porta 465)
# ═══════════════════════════════════════════════════════════════════════

def _send_email_smtp(to_email, subject, body_html, body_text=None):
    """Envia email via SMTP. Retorna True/False (nao bloqueia caller em erro)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "contato@sistemaponto.com")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_pass:
        print(f"[EMAIL] SMTP_PASSWORD nao configurado. Email para {to_email} NAO enviado.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Sistema Ponto <{smtp_user}>"
    msg['To'] = to_email

    if body_text:
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        print(f"[EMAIL] Enviado: '{subject}' para {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] FALHA ao enviar para {to_email}: {e}")
        return False


def _email_template_base(title, intro_html, cta_text, cta_link, footer_note=""):
    """Template HTML base para emails de onboarding da empresa."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.05);">
        <tr><td style="padding:32px 40px 16px;background:linear-gradient(135deg,#4a9eff 0%,#3a7bcf 100%);color:#fff;">
          <div style="font-size:14px;opacity:0.85;letter-spacing:0.5px;">SISTEMA PONTO</div>
          <h1 style="margin:8px 0 0;font-size:22px;font-weight:600;">{title}</h1>
        </td></tr>
        <tr><td style="padding:32px 40px;color:#1a1a1a;font-size:15px;line-height:1.6;">
          {intro_html}
          <p style="text-align:center;margin:32px 0;">
            <a href="{cta_link}" style="display:inline-block;background:#4a9eff;color:#ffffff;text-decoration:none;padding:14px 36px;border-radius:8px;font-weight:600;font-size:15px;">{cta_text}</a>
          </p>
          <p style="color:#666;font-size:12px;margin-top:24px;">Ou copie e cole este endereco no navegador:<br>
            <span style="color:#4a9eff;word-break:break-all;">{cta_link}</span>
          </p>
        </td></tr>
        <tr><td style="padding:20px 40px 32px;border-top:1px solid #eee;color:#888;font-size:12px;line-height:1.5;">
          <p style="margin:0;">{footer_note}</p>
          <p style="margin:8px 0 0;">Sistema Ponto - Extracao inteligente de cartoes de ponto e holerites<br>
          <a href="https://sistemaponto.com" style="color:#888;">sistemaponto.com</a> - Suporte: <a href="https://wa.me/5554999427282" style="color:#888;">WhatsApp (54) 99942-7282</a></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send_org_admin_welcome_email(to_email, org_name, invite_link):
    """Envia email para o admin da nova empresa definir senha e cadastrar cartao."""
    subject = f"Bem-vindo ao Sistema Ponto - {org_name}"
    intro = f"""
      <p>Ola,</p>
      <p>Sua conta de administrador da empresa <strong>{org_name}</strong> foi criada no Sistema Ponto.</p>
      <p>Para comecar a usar, defina uma senha clicando no botao abaixo. Depois disso, voce podera cadastrar a forma de pagamento e convidar funcionarios.</p>
    """
    html = _email_template_base(
        title=f"Bem-vindo, {org_name}",
        intro_html=intro,
        cta_text="Definir minha senha",
        cta_link=invite_link,
        footer_note="Caso voce nao tenha solicitado este acesso, ignore este e-mail.",
    )
    text = f"""Bem-vindo ao Sistema Ponto!

Sua conta de administrador da empresa {org_name} foi criada.
Para comecar, defina uma senha em:

{invite_link}

Caso nao tenha solicitado este acesso, ignore este e-mail.
"""
    return _send_email_smtp(to_email, subject, html, text)


def send_org_member_invite_email(to_email, org_name, invite_link, invited_by_email):
    """Envia email para funcionario convidado por uma empresa."""
    subject = f"Voce foi convidado para {org_name} no Sistema Ponto"
    intro = f"""
      <p>Ola,</p>
      <p><strong>{invited_by_email}</strong> convidou voce para fazer parte de <strong>{org_name}</strong> no Sistema Ponto.</p>
      <p>Como funcionario da empresa, voce tera acesso ao sistema com uso ilimitado de paginas - a empresa paga pelo uso ao final de cada mes.</p>
      <p>Para aceitar o convite e criar sua senha:</p>
    """
    html = _email_template_base(
        title=f"Convite para {org_name}",
        intro_html=intro,
        cta_text="Aceitar convite",
        cta_link=invite_link,
        footer_note="Se voce nao esperava este convite, ignore este e-mail.",
    )
    text = f"""Voce foi convidado para {org_name} no Sistema Ponto.

{invited_by_email} adicionou voce como funcionario.
Para criar sua senha:

{invite_link}

Se voce nao esperava este convite, ignore este e-mail.
"""
    return _send_email_smtp(to_email, subject, html, text)


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS PUBLICOS DE ACEITE DE CONVITE
# Sem autenticacao - o token no URL e a credencial
# ═══════════════════════════════════════════════════════════════════════

def _register_invite_endpoints(app):
    """Endpoints publicos /api/org/invite/<token>/* para aceitar convite."""

    @app.route('/api/org/invite/<token>/info', methods=['GET'])
    def org_invite_info(token):
        """Valida o token e retorna info da empresa + usuario (publico)."""
        if not token or len(token) < 10:
            return jsonify({"msg": "Token invalido."}), 400

        user = _User.query.filter_by(password_reset_token=token).first()
        if not user:
            return jsonify({"msg": "Convite invalido ou ja utilizado."}), 404

        # Verifica expiracao - 7 dias
        if user.password_reset_sent_at:
            sent = user.password_reset_sent_at
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - sent).days
            if age_days > 7:
                return jsonify({"msg": "Convite expirado. Solicite um novo."}), 410

        # Se nao tem org, este token nao e de convite de empresa
        if not user.organization_id:
            return jsonify({"msg": "Este token nao e um convite de empresa."}), 400

        org = _Organization.query.get(user.organization_id)
        if not org:
            return jsonify({"msg": "Empresa nao encontrada."}), 404

        return jsonify({
            "email": user.email,
            "org_name": org.name,
            "org_role": user.org_role,
            "is_admin": user.org_role == "admin",
        }), 200


    @app.route('/api/org/invite/<token>/accept', methods=['POST'])
    def org_invite_accept(token):
        """Aceita o convite: define senha e retorna access_token para auto-login."""
        from werkzeug.security import generate_password_hash
        from flask_jwt_extended import create_access_token

        if not token or len(token) < 10:
            return jsonify({"msg": "Token invalido."}), 400

        try:
            data = request.get_json() or {}
            password = (data.get('password') or '').strip()

            if len(password) < 8:
                return jsonify({"msg": "Senha deve ter no minimo 8 caracteres."}), 400

            user = _User.query.filter_by(password_reset_token=token).first()
            if not user:
                return jsonify({"msg": "Convite invalido ou ja utilizado."}), 404

            if user.password_reset_sent_at:
                sent = user.password_reset_sent_at
                if sent.tzinfo is None:
                    sent = sent.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - sent).days > 7:
                    return jsonify({"msg": "Convite expirado."}), 410

            if not user.organization_id:
                return jsonify({"msg": "Token invalido."}), 400

            # Define senha + limpa token
            user.password_hash = generate_password_hash(password)
            user.password_reset_token = None
            user.password_reset_sent_at = None
            if hasattr(user, 'email_verified'):
                user.email_verified = True
            user.is_active = True
            _db.session.commit()

            # Auto-login: emite access_token
            access_token = create_access_token(identity=user.email)

            print(f"[ORG-INVITE] {user.email} aceitou convite da empresa #{user.organization_id}")
            return jsonify({
                "msg": "Senha definida com sucesso.",
                "access_token": access_token,
                "user": {
                    "email": user.email,
                    "organization_id": user.organization_id,
                    "org_role": user.org_role,
                },
            }), 200

        except Exception as e:
            _db.session.rollback()
            print(f"[ORG-INVITE] Erro accept: {e}")
            traceback.print_exc()
            return jsonify({"msg": "Erro ao definir senha."}), 500
