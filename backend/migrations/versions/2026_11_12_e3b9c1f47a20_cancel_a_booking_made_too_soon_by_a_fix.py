"""cancel a booking made too soon by a fixed pickup

Revision ID: e3b9c1f47a20
Revises: d7a2e5c813f6
Create Date: 2026-11-12 23:30:00.000000

Decided 12 Nov: when a no-show is fixed to picked up, a later booking now less
than the pickup gap after it is cancelled, with the reason "pickup_fixed".
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e3b9c1f47a20'
down_revision: Union[str, Sequence[str], None] = 'd7a2e5c813f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f('ck_bookings_cancel_reason_is_known'), 'bookings', type_='check')
    op.create_check_constraint(
        op.f('ck_bookings_cancel_reason_is_known'),
        'bookings',
        "cancel_reason IN ('student', 'day_closed', 'walk_in', 'pickup_fixed')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_bookings_cancel_reason_is_known'), 'bookings', type_='check')
    op.create_check_constraint(
        op.f('ck_bookings_cancel_reason_is_known'),
        'bookings',
        "cancel_reason IN ('student', 'day_closed', 'walk_in')",
    )
