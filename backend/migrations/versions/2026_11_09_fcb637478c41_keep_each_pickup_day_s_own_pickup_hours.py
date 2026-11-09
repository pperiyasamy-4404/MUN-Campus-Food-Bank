"""keep each pickup day's own pickup hours

Revision ID: fcb637478c41
Revises: 22ef6889a3d0
Create Date: 2026-11-09 16:09:13.753955

Walk-ins are served only during pickup hours, 3:30 to 5:30 pm with the sample
hours (the user's answer, 9 Nov). So each pickup day keeps its own pickup hours,
like its booking and no-show times, and a change to the weekly hours never moves
a day that's already made.

Days made before this get the hours of their weekday from pickup_hours, read as
Newfoundland clock times. Then the columns become required.

Three new rules keep a day's times in order: booking closes, pickup starts,
pickup ends, no-shows. The old rule "no-show after booking closes" follows from
them, so it can never be the only rule broken, and it's dropped.

Written by hand: Alembic would add required columns straight away, which fails
on a table that already has rows, and it doesn't notice new CHECK rules.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcb637478c41'
down_revision: Union[str, Sequence[str], None] = '22ef6889a3d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pickup_days', sa.Column('pickup_starts_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('pickup_days', sa.Column('pickup_ends_at', sa.DateTime(timezone=True), nullable=True))

    # date + time is a clock time with no zone. AT TIME ZONE reads it as St. John's time.
    op.execute(
        """
        UPDATE pickup_days AS d
        SET pickup_starts_at = (d.pickup_date + h.starts_at) AT TIME ZONE 'America/St_Johns',
            pickup_ends_at = (d.pickup_date + h.ends_at) AT TIME ZONE 'America/St_Johns'
        FROM pickup_hours AS h
        WHERE h.weekday = EXTRACT(ISODOW FROM d.pickup_date)
        """
    )
    op.alter_column('pickup_days', 'pickup_starts_at', nullable=False)
    op.alter_column('pickup_days', 'pickup_ends_at', nullable=False)

    op.create_check_constraint(
        op.f('ck_pickup_days_pickup_starts_after_booking_closes'),
        'pickup_days',
        "booking_closes_at <= pickup_starts_at",
    )
    op.create_check_constraint(
        op.f('ck_pickup_days_pickup_ends_after_it_starts'),
        'pickup_days',
        "pickup_starts_at < pickup_ends_at",
    )
    op.create_check_constraint(
        op.f('ck_pickup_days_no_show_after_pickup_ends'),
        'pickup_days',
        "pickup_ends_at <= no_show_at",
    )
    op.drop_constraint(op.f('ck_pickup_days_no_show_after_booking_closes'), 'pickup_days', type_='check')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_check_constraint(
        op.f('ck_pickup_days_no_show_after_booking_closes'),
        'pickup_days',
        "booking_closes_at < no_show_at",
    )
    op.drop_constraint(op.f('ck_pickup_days_no_show_after_pickup_ends'), 'pickup_days', type_='check')
    op.drop_constraint(op.f('ck_pickup_days_pickup_ends_after_it_starts'), 'pickup_days', type_='check')
    op.drop_constraint(op.f('ck_pickup_days_pickup_starts_after_booking_closes'), 'pickup_days', type_='check')
    op.drop_column('pickup_days', 'pickup_ends_at')
    op.drop_column('pickup_days', 'pickup_starts_at')
