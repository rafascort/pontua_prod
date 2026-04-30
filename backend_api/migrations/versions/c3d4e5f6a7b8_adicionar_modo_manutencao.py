"""Adicionar modo manutencao

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-26 10:00:00.000000

Cria a tabela `maintenance_window` para programar e rastrear janelas de
manutenção do sistema.

Para aplicar:
    cd /opt/pontua/AutoPonto/backend_api
    source venv/bin/activate
    flask db upgrade

Para reverter:
    flask db downgrade b2c3d4e5f6a7
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_window',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('announcement_id', sa.Integer(),
                  sa.ForeignKey('announcement.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('actually_ended_at', sa.DateTime(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='scheduled'),
        sa.Column('is_emergency', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_admin', sa.String(length=120), nullable=True),
    )
    op.create_index('ix_maint_status', 'maintenance_window', ['status'])
    op.create_index('ix_maint_starts_at', 'maintenance_window', ['starts_at'])
    op.create_index('ix_maint_ends_at', 'maintenance_window', ['ends_at'])


def downgrade():
    op.drop_index('ix_maint_ends_at', table_name='maintenance_window')
    op.drop_index('ix_maint_starts_at', table_name='maintenance_window')
    op.drop_index('ix_maint_status', table_name='maintenance_window')
    op.drop_table('maintenance_window')
