#!/usr/bin/env python3
"""
apply_backend_patch.py

Aplica no auth_service.py:
  1. Leitura do parâmetro 'when' no /api/change-plan.
  2. Ramificação do upgrade: se when=='now' (proração imediata) ou
     when=='period_end' (cai no caminho de schedule).
  3. Mensagem/tipo de retorno do agendamento ajustados para servir
     tanto downgrade quanto upgrade agendado.
  4. Novo endpoint /api/preview-change-plan (prévia de fatura, não cobra).

Seguro: faz backup, verifica que cada bloco esperado existe
exatamente 1 vez antes de gravar. Idempotente: roda mais de uma vez
sem efeito colateral (detecta blocos já aplicados).
"""
import shutil, sys

PATH = "/opt/pontua/AutoPonto/backend_api/auth_service.py"

# ─── (1) Adicionar leitura de 'when' logo após new_price_id ───
OLD_1 = """    data = request.get_json() or {}
    new_price_id = data.get('priceId')
    if not new_price_id or new_price_id not in PRICE_ID_TO_PLAN_NAME:
        return jsonify({"msg": "Price ID inválido."}), 400"""

NEW_1 = """    data = request.get_json() or {}
    new_price_id = data.get('priceId')
    when = data.get('when') or 'now'  # 'now' (proração imediata) ou 'period_end' (agendado)
    if when not in ('now', 'period_end'):
        when = 'now'
    if not new_price_id or new_price_id not in PRICE_ID_TO_PLAN_NAME:
        return jsonify({"msg": "Price ID inválido."}), 400"""

# ─── (2) Ramificar upgrade: só faz modify imediato se when=='now' ───
OLD_2 = """        cur_rank = PLAN_RANK.get(current_plan, 0)
        new_rank = PLAN_RANK.get(new_plan, 0)

        # UPGRADE: imediato
        if new_rank > cur_rank:"""

NEW_2 = """        cur_rank = PLAN_RANK.get(current_plan, 0)
        new_rank = PLAN_RANK.get(new_plan, 0)
        is_upgrade = new_rank > cur_rank

        # UPGRADE imediato (proração) — só se o cliente escolheu "agora".
        # Se for upgrade com when='period_end', cai no fluxo de schedule abaixo.
        if is_upgrade and when == 'now':"""

# ─── (3) Mensagem/tipo do retorno do agendamento (serve down e up agendado) ───
OLD_3 = """        return jsonify({"msg": f"Downgrade para {new_plan} agendado para o fim do ciclo atual.",
                        "type": "downgrade", "plan": new_plan, "effective": "period_end"})"""

NEW_3 = """        op_type = "upgrade" if is_upgrade else "downgrade"
        return jsonify({"msg": f"Mudança para {new_plan} agendada para o fim do ciclo atual.",
                        "type": op_type, "plan": new_plan, "effective": "period_end"})"""

# ─── (4) Novo endpoint /api/preview-change-plan, antes do /api/subscription-status ───
OLD_4 = """@app.route('/api/subscription-status', methods=['GET'])
@jwt_required()
def subscription_status():"""

NEW_4 = """@app.route('/api/preview-change-plan', methods=['POST'])
@jwt_required()
def preview_change_plan():
    \"\"\"Prévia de fatura para upgrade imediato (proração). Não cobra nada.\"\"\"
    data = request.get_json() or {}
    new_price_id = data.get('priceId')
    if not new_price_id or new_price_id not in PRICE_ID_TO_PLAN_NAME:
        return jsonify({"msg": "Price ID inválido."}), 400

    new_plan  = PRICE_ID_TO_PLAN_NAME[new_price_id]
    new_extra = PLAN_NAME_TO_EXTRA_PRICE_ID.get(new_plan)
    if not new_extra:
        return jsonify({"msg": "Plano não configurado."}), 500

    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    if not user or not user.stripe_customer_id:
        return jsonify({"msg": "Cliente Stripe não encontrado."}), 404

    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, status='active', limit=1
        )
        if not subs.data:
            return jsonify({"msg": "Nenhuma assinatura ativa."}), 404
        sub = subs.data[0]

        lic = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') != 'metered'), None)
        met = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') == 'metered'), None)
        if not lic:
            return jsonify({"msg": "Item licenciado não encontrado."}), 500

        items = [{'id': lic['id'], 'price': new_price_id, 'quantity': 1}]
        if met:
            items.append({'id': met['id'], 'price': new_extra})

        # API nova (stripe>=8) tem create_preview; versões antigas, Invoice.upcoming
        try:
            prev = stripe.Invoice.create_preview(
                customer=user.stripe_customer_id,
                subscription=sub.id,
                subscription_details={
                    "items": items,
                    "proration_behavior": "create_prorations",
                },
            )
        except AttributeError:
            prev = stripe.Invoice.upcoming(
                customer=user.stripe_customer_id,
                subscription=sub.id,
                subscription_items=items,
                subscription_proration_behavior="create_prorations",
            )

        return jsonify({
            "amount_due": prev.get("amount_due", 0),
            "currency":   prev.get("currency", "brl"),
        })
    except stripe.StripeError as e:
        print(f"Stripe Error preview-change-plan: {e}")
        return jsonify({"msg": f"Erro: {getattr(e, 'user_message', None) or 'Tente novamente.'}"}), 500
    except Exception as e:
        import traceback
        print(f"Erro preview-change-plan: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno na prévia."}), 500


@app.route('/api/subscription-status', methods=['GET'])
@jwt_required()
def subscription_status():"""

# Marcadores de "já aplicado" (para idempotência) — se já existirem, pula o passo.
ALREADY_1 = "when = data.get('when') or 'now'"
ALREADY_2 = "is_upgrade = new_rank > cur_rank"
ALREADY_3 = '"type": op_type, "plan": new_plan, "effective": "period_end"'
ALREADY_4 = "def preview_change_plan():"


def apply(src: str) -> str:
    steps = [
        ("1) leitura de 'when'",              OLD_1, NEW_1, ALREADY_1),
        ("2) ramificação do upgrade",         OLD_2, NEW_2, ALREADY_2),
        ("3) mensagem/tipo do agendamento",   OLD_3, NEW_3, ALREADY_3),
        ("4) endpoint preview-change-plan",   OLD_4, NEW_4, ALREADY_4),
    ]
    for name, old, new, marker in steps:
        if marker in src:
            print(f"  [skip] {name}: já aplicado")
            continue
        n = src.count(old)
        if n != 1:
            print(f"ABORTADO em {name}: achei {n} ocorrências do bloco (esperava 1).")
            print("Nada foi alterado.")
            sys.exit(1)
        src = src.replace(old, new)
        print(f"  [ok]   {name}")
    return src


def main():
    src = open(PATH, encoding="utf-8").read()
    new_src = apply(src)
    if new_src == src:
        print("Nada a fazer — patch já estava todo aplicado.")
        return
    shutil.copy(PATH, PATH + ".bak_change_plan_v2")
    open(PATH, "w", encoding="utf-8").write(new_src)
    print(f"OK: patch aplicado. Backup em {PATH}.bak_change_plan_v2")


if __name__ == "__main__":
    main()
