"""email lifecycle: created_at, last_activity_at, last_renewal_at, email_opt_out, email_event"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2m3lifecycle'
down_revision = 'c7e9addextras'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Colunas novas. created_at entra SEM default de proposito: com default,
    #    o Postgres preencheria toda a base com a data de hoje e a regua de
    #    e-mails dispararia para todos os usuarios antigos.
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('last_activity_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('last_renewal_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('email_opt_out', sa.Boolean(),
                                    nullable=False, server_default=sa.text('false')))

    # 2) Backfill: data do e-mail de verificacao como aproximacao do cadastro.
    op.execute('''
        UPDATE "user"
           SET created_at = email_verification_sent_at
         WHERE email_verification_sent_at IS NOT NULL
    ''')

    # 3) A partir de agora, todo cadastro novo grava a data automaticamente.
    op.execute('ALTER TABLE "user" ALTER COLUMN created_at SET DEFAULT now()')

    # 4) Historico de e-mails: fonte do painel admin e da idempotencia.
    op.create_table(
        'email_event',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='sent'),
        sa.Column('sent_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('meta', sa.Text(), nullable=True),
    )
    op.create_index('ix_email_event_user_id', 'email_event', ['user_id'])
    op.create_index('ix_email_event_user_type', 'email_event',
                    ['user_id', 'email_type'])
    op.create_index('ix_email_event_sent_at', 'email_event', ['sent_at'])


def downgrade():
    op.drop_index('ix_email_event_sent_at', table_name='email_event')
    op.drop_index('ix_email_event_user_type', table_name='email_event')
    op.drop_index('ix_email_event_user_id', table_name='email_event')
    op.drop_table('email_event')
    op.drop_column('user', 'email_opt_out')
    op.drop_column('user', 'last_renewal_at')
    op.drop_column('user', 'last_activity_at')
    op.drop_column('user', 'created_at')
