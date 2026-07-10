"""add strategy archived flag

Revision ID: b7c4e2a91d03
Revises: 54e815394bf2
Create Date: 2026-07-10 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c4e2a91d03'
down_revision: Union[str, Sequence[str], None] = '54e815394bf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'strategies',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('strategies', 'archived')
