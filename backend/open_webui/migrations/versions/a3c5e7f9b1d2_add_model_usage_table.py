"""Add model_usage table

Revision ID: a3c5e7f9b1d2
Revises: 0bd252b206fb
Create Date: 2026-11-03 10:00:00.000000

Ledger of tokens per finished model call, used to enforce usage quotas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from open_webui.migrations.util import get_existing_tables

revision: str = 'a3c5e7f9b1d2'
down_revision: str | None = '0bd252b206fb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if 'model_usage' in get_existing_tables():
        return
    op.create_table(
        'model_usage',
        sa.Column('id', sa.Text(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index('model_usage_user_created_idx', 'model_usage', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('model_usage_user_created_idx', table_name='model_usage')
    op.drop_table('model_usage')
