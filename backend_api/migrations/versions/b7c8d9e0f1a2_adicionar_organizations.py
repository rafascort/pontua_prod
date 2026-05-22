"""Adicionar suporte a organizacoes (empresas)

Revision ID: b7c8d9e0f1a2
Revises: COLE_AQUI_O_HEAD_ATUAL
Create Date: 2026-05-18 00:00:00.000000

Esta migration:
  - Cria a tabela `organization` (escritórios / empresas clientes)
  - Adiciona 3 colunas em `user`:
      organization_id  (FK para organization, nullable — usuarios avulsos ficam NULL)
      org_role         ('admin' | 'member' | NULL)
      can_process      (bool, default true — controla se admin da empresa processa PDFs)

Para aplicar:
    cd /opt/pontua/AutoPonto/backend_api
    source venv/bin/activate
    flask db upgrade

Para reverter:
    flask db downgrade COLE_AQUI_O_HEAD_ATUAL
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c8d9e0f1a2'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Tabela organization ───────────────────────────────────────
    op.create_table(
        'organization',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('legal_name', sa.String(length=180), nullable=True),
        sa.Column('cnpj', sa.String(length=18), nullable=True),
        sa.Column('billing_email', sa.String(length=120), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('stripe_customer_id', sa.String(length=120), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=120), nullable=True),
        sa.Column('stripe_price_id', sa.String(length=120), nullable=True),
        sa.Column('plan_status', sa.String(length=50), nullable=False,
                  server_default='awaiting_setup'),
        sa.Column('price_per_page_cents', sa.Integer(), nullable=False,
                  server_default='62'),
        sa.Column('pending_price_per_page_cents', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('next_reset_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_admin_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('cnpj', name='uq_organization_cnpj'),
        sa.UniqueConstraint('stripe_customer_id',
                            name='uq_organization_stripe_customer_id'),
    )
    op.create_index('ix_organization_is_active', 'organization', ['is_active'])
    op.create_index('ix_organization_plan_status', 'organization', ['plan_status'])

    # ── 2. Colunas novas em user ─────────────────────────────────────
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('org_role', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('can_process', sa.Boolean(), nullable=False,
                                       server_default=sa.text('true')))
        batch_op.create_foreign_key(
            'fk_user_organization_id',
            'organization',
            ['organization_id'], ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index('ix_user_organization_id', ['organization_id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index('ix_user_organization_id')
        batch_op.drop_constraint('fk_user_organization_id', type_='foreignkey')
        batch_op.drop_column('can_process')
        batch_op.drop_column('org_role')
        batch_op.drop_column('organization_id')

    op.drop_index('ix_organization_plan_status', table_name='organization')
    op.drop_index('ix_organization_is_active', table_name='organization')
    op.drop_table('organization')
