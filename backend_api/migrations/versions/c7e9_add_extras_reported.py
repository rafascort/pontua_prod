"""Add extras_reported column to user (display fiel de extras já cobrados)

Revision ID: c7e9addextras
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7e9addextras'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'extras_reported', sa.Integer(), nullable=False, server_default='0'
        ))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('extras_reported')
