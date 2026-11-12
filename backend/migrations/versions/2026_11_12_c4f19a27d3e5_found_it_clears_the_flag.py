"""found it clears the out-of-stock flag for every bag

Revision ID: c4f19a27d3e5
Revises: b81d4c2e9a70
Create Date: 2026-11-12 22:00:00.000000

What-could-go-wrong problem 6, the open question (decided 12 Nov): when a
volunteer taps Found it on food someone else marked out of stock, the flag
comes off every bag. The food stays at 0 until someone checks the shelf, and
found_at tells the Stock page to ask for that check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f19a27d3e5'
down_revision: Union[str, Sequence[str], None] = 'b81d4c2e9a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('varieties', sa.Column('found_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('varieties', 'found_at')
