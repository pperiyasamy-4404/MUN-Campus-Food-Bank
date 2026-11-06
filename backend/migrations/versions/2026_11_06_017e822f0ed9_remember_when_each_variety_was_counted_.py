"""remember when each variety was counted, and by whom

Revision ID: 017e822f0ed9
Revises: 8be36cf65217
Create Date: 2026-11-06 15:48:34.307803

Step 4, items and stock: volunteers count the shelf before each booking window
opens (I8). Each variety remembers its last count, so the stock page can show
what hasn't been counted since the last pickup.

Alembic doesn't notice new CHECK rules by itself, so that line is written by hand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017e822f0ed9'
down_revision: Union[str, Sequence[str], None] = '8be36cf65217'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('varieties', sa.Column('counted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('varieties', sa.Column('counted_by_staff_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_varieties_counted_by_staff_id'), 'varieties', 'staff', ['counted_by_staff_id'], ['id'])

    # Written by hand.
    op.create_check_constraint(
        op.f('ck_varieties_count_has_a_counter'),
        'varieties',
        "(counted_at IS NULL) = (counted_by_staff_id IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_varieties_count_has_a_counter'), 'varieties', type_='check')
    op.drop_constraint(op.f('fk_varieties_counted_by_staff_id'), 'varieties', type_='foreignkey')
    op.drop_column('varieties', 'counted_by_staff_id')
    op.drop_column('varieties', 'counted_at')
