"""widen history.perc_income_day to Numeric(16, 6)

Revision ID: c3a91f7e2b14
Revises: b7c4e2a91d03
Create Date: 2026-07-19 12:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a91f7e2b14'
down_revision: Union[str, Sequence[str], None] = 'b7c4e2a91d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'history',
        'perc_income_day',
        existing_type=sa.Numeric(precision=7, scale=3),
        type_=sa.Numeric(precision=16, scale=6),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'history',
        'perc_income_day',
        existing_type=sa.Numeric(precision=16, scale=6),
        type_=sa.Numeric(precision=7, scale=3),
        existing_nullable=True,
    )
