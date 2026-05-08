from auth_service import app, db, User, update_user_plan_from_subscription, sync_user_billing_cycle
import stripe

EMAIL = 'gspericiacontabil@gmail.com'

with app.app_context():
    user = User.query.filter_by(email=EMAIL).first()
    print(f"ANTES: plan_status={user.plan_status}, page_count={user.page_count}, customer={user.stripe_customer_id}")

    subs = stripe.Subscription.list(customer=user.stripe_customer_id, status='active', limit=5)
    print(f"Subs ativas no Stripe: {len(subs.data)}")
    for s in subs.data:
        print(f"  - {s.id} | status={s.status}")

    if not subs.data:
        print("ERRO: nenhuma sub ativa encontrada no Stripe!")
    else:
        sub = subs.data[0]
        update_user_plan_from_subscription(user, sub)
        sync_user_billing_cycle(user.email)
        db.session.commit()
        print(f"DEPOIS: plan_status={user.plan_status}, page_count={user.page_count}")
        print("OK - plano restaurado!")
