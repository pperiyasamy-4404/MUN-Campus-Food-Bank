"""say who is packing a bag

Revision ID: b81d4c2e9a70
Revises: a7c3e91f0b24
Create Date: 2026-11-12 14:00:00.000000

What-could-go-wrong problem 7 (decided 12 Nov): when a volunteer opens a bag
to pack it, the queue says "Sam is packing", and anyone else who opens it is
warned first, so two people don't fill two bags for one booking.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b81d4c2e9a70'
down_revision: Union[str, Sequence[str], None] = 'a7c3e91f0b24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bookings', sa.Column('packing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bookings', sa.Column('packing_by_staff_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_bookings_packing_by_staff_id'), 'bookings', 'staff', ['packing_by_staff_id'], ['id'])
    op.create_check_constraint(
        op.f('ck_bookings_packing_has_a_volunteer'),
        'bookings',
        '(packing_started_at IS NULL) = (packing_by_staff_id IS NULL)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_bookings_packing_has_a_volunteer'), 'bookings', type_='check')
    op.drop_constraint(op.f('fk_bookings_packing_by_staff_id'), 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'packing_by_staff_id')
    op.drop_column('bookings', 'packing_started_at')
