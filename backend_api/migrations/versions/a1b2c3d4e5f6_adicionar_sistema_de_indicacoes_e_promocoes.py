"""Adicionar sistema de indicacoes e promocoes

Revision ID: a1b2c3d4e5f6
Revises: 5f971c7710ec
Create Date: 2026-04-23 10:00:00.000000

Esta migration:
  - Adiciona 3 colunas na tabela `user` (referral_code, referred_by_code, discount_credits)
  - Cria a tabela `referral` (histórico de indicações)
  - Cria a tabela `promotion` (campanhas dinâmicas do admin)
  - Cria a tabela `promotion_metric` (tracking de impressões/cliques)

Para aplicar:
    cd /opt/pontua/AutoPonto/backend_api
    source venv/bin/activate
    flask db upgrade

Para reverter:
    flask db downgrade 5f971c7710ec
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '5f971c7710ec'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Colunas novas na tabela user ──────────────────────────────────
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'referral_code', sa.String(length=20), nullable=True
        ))
        batch_op.add_column(sa.Column(
            'referred_by_code', sa.String(length=20), nullable=True
        ))
        batch_op.add_column(sa.Column(
            'discount_credits', sa.Integer(), nullable=False,
            server_default='0'
        ))
        batch_op.create_unique_constraint(
            'uq_user_referral_code', ['referral_code']
        )

    # ── 2. Tabela referral ───────────────────────────────────────────────
    op.create_table(
        'referral',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('referrer_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('referred_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('referrer_code', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='pending'),
        sa.Column('plan_at_conversion', sa.String(length=50), nullable=True),
        sa.Column('discount_granted_pct', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('converted_at', sa.DateTime(), nullable=True),
        sa.Column('credit_applied', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.UniqueConstraint('referred_id', name='uq_referral_referred_id'),
    )
    op.create_index('ix_referral_referrer_id', 'referral', ['referrer_id'])
    op.create_index('ix_referral_status', 'referral', ['status'])

    # ── 3. Tabela promotion ──────────────────────────────────────────────
    op.create_table(
        'promotion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('badge_label', sa.String(length=50), nullable=False,
                  server_default='Promoção'),
        sa.Column('badge_color', sa.String(length=20), nullable=False,
                  server_default='emerald'),
        sa.Column('icon', sa.String(length=50), nullable=False,
                  server_default='Sparkles'),
        sa.Column('discount_hint', sa.String(length=60), nullable=True),
        sa.Column('cta_type', sa.String(length=20), nullable=False,
                  server_default='none'),
        sa.Column('cta_value', sa.String(length=500), nullable=True),
        sa.Column('cta_label', sa.String(length=80), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_admin', sa.String(length=120), nullable=True),
    )
    op.create_index('ix_promotion_active', 'promotion', ['active'])
    op.create_index('ix_promotion_priority', 'promotion', ['priority'])

    # ── 4. Tabela promotion_metric ──────────────────────────────────────
    op.create_table(
        'promotion_metric',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('promotion_id', sa.Integer(),
                  sa.ForeignKey('promotion.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_metric_promotion_id', 'promotion_metric', ['promotion_id'])
    op.create_index('ix_metric_event_type', 'promotion_metric', ['event_type'])
    op.create_index('ix_metric_created_at', 'promotion_metric', ['created_at'])


def downgrade():
    op.drop_index('ix_metric_created_at', table_name='promotion_metric')
    op.drop_index('ix_metric_event_type', table_name='promotion_metric')
    op.drop_index('ix_metric_promotion_id', table_name='promotion_metric')
    op.drop_table('promotion_metric')

    op.drop_index('ix_promotion_priority', table_name='promotion')
    op.drop_index('ix_promotion_active', table_name='promotion')
    op.drop_table('promotion')

    op.drop_index('ix_referral_status', table_name='referral')
    op.drop_index('ix_referral_referrer_id', table_name='referral')
    op.drop_table('referral')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_referral_code', type_='unique')
        batch_op.drop_column('discount_credits')
        batch_op.drop_column('referred_by_code')
        batch_op.drop_column('referral_code')
