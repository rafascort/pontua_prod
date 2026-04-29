"""Adicionar sistema de avisos

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25 10:00:00.000000

Esta migration:
  - Cria a tabela `announcement` (avisos do admin)
  - Cria a tabela `announcement_ack` (registros de confirmação por usuário)

Para aplicar:
    cd /opt/pontua/AutoPonto/backend_api
    source venv/bin/activate
    flask db upgrade

Para reverter:
    flask db downgrade a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Tabela announcement ──────────────────────────────────────────
    op.create_table(
        'announcement',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False,
                  server_default='info'),
        sa.Column('frequency', sa.String(length=20), nullable=False,
                  server_default='once'),
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
    op.create_index('ix_announcement_active', 'announcement', ['active'])
    op.create_index('ix_announcement_severity', 'announcement', ['severity'])

    # ── 2. Tabela announcement_ack ──────────────────────────────────────
    op.create_table(
        'announcement_ack',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('announcement_id', sa.Integer(),
                  sa.ForeignKey('announcement.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_ack_announcement_id', 'announcement_ack', ['announcement_id'])
    op.create_index('ix_ack_user_id', 'announcement_ack', ['user_id'])
    op.create_index('ix_ack_session_id', 'announcement_ack', ['session_id'])

    # Para "once": só pode ter 1 ack por (announcement, user) sem session
    # Para "every_session": muitos acks com sessions diferentes
    # Por isso a constraint é parcial — em PostgreSQL fazemos um partial index único:
    op.execute(
        "CREATE UNIQUE INDEX uq_ack_once "
        "ON announcement_ack (announcement_id, user_id) "
        "WHERE session_id IS NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_ack_once")
    op.drop_index('ix_ack_session_id', table_name='announcement_ack')
    op.drop_index('ix_ack_user_id', table_name='announcement_ack')
    op.drop_index('ix_ack_announcement_id', table_name='announcement_ack')
    op.drop_table('announcement_ack')

    op.drop_index('ix_announcement_severity', table_name='announcement')
    op.drop_index('ix_announcement_active', table_name='announcement')
    op.drop_table('announcement')
