"""remember what each bag was packed with

Revision ID: c250b0a6f9de
Revises: 017e822f0ed9
Create Date: 2026-11-07 11:12:44.613551

Step 6, packing. Each bag remembers who packed it, which booked food wasn't on
the shelf, and which substitute replaced it, so the sticky note can be shown
again later (U4, U8). Each variety remembers when a volunteer found none on the
shelf, so every other bag with it is flagged in the packing queue (U7).

Alembic doesn't notice new CHECK rules by itself, so those lines are written by hand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c250b0a6f9de'
down_revision: Union[str, Sequence[str], None] = '017e822f0ed9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('booking_items', sa.Column('missing', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('booking_substitutes', sa.Column('replaces_variety_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_booking_substitutes_booking_id_replaces_variety_id'), 'booking_substitutes', 'booking_items', ['booking_id', 'replaces_variety_id'], ['booking_id', 'variety_id'])
    op.add_column('bookings', sa.Column('packed_by_staff_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_bookings_packed_by_staff_id'), 'bookings', 'staff', ['packed_by_staff_id'], ['id'])
    op.add_column('varieties', sa.Column('ran_out_at', sa.DateTime(timezone=True), nullable=True))

    # Written by hand.
    op.create_check_constraint(
        op.f('ck_bookings_packed_by_a_volunteer'),
        'bookings',
        "(packed_at IS NULL) = (packed_by_staff_id IS NULL)",
    )
    op.create_check_constraint(
        op.f('ck_booking_items_missing_within_quantity'),
        'booking_items',
        "missing BETWEEN 0 AND quantity",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_booking_items_missing_within_quantity'), 'booking_items', type_='check')
    op.drop_constraint(op.f('ck_bookings_packed_by_a_volunteer'), 'bookings', type_='check')
    op.drop_column('varieties', 'ran_out_at')
    op.drop_constraint(op.f('fk_bookings_packed_by_staff_id'), 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'packed_by_staff_id')
    op.drop_constraint(op.f('fk_booking_substitutes_booking_id_replaces_variety_id'), 'booking_substitutes', type_='foreignkey')
    op.drop_column('booking_substitutes', 'replaces_variety_id')
    op.drop_column('booking_items', 'missing')
