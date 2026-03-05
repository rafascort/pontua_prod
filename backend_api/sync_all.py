# /opt/pontua/AutoPonto/backend_api/sync_all.py
import stripe
import os
from dotenv import load_dotenv
from auth_service import app, db, User, sync_user_billing_cycle

load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

def run_sync():
    with app.app_context():
        # Busca usuários que já têm Stripe ID mas ainda não têm data de reset
        users = User.query.filter(User.stripe_customer_id.isnot(None)).all()
        print(f"Sincronizando {len(users)} usuários...")
        
        for user in users:
            success = sync_user_billing_cycle(user.email)
            if success:
                print(f"Sucesso: {user.email}")
            else:
                print(f"Falha ou sem assinatura ativa: {user.email}")

if __name__ == "__main__":
    run_sync()
