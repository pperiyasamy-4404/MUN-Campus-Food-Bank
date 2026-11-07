"""add walk-ins and food handed over at the counter

Revision ID: 8ed315f3aef8
Revises: c250b0a6f9de
Create Date: 2026-11-07 12:40:02.290974

Step 7, the counter. walk_ins records students served without a booking (W1).
counter_items records food handed over that wasn't in a packed bag: extras
(E3, E4), a student's choice for a gap (U6), and what a walk-in takes.

counter_items keeps "one of each extra item" as a database rule. For that it
copies the item and is_extra onto each row, and links to the pairs
(variety, item) and (item, is_extra), so the copies are always right. Those
links need the two new unique rules on varieties and items to exist first, so
the order below was changed by hand: Alembic made them after the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ed315f3aef8'
down_revision: Union[str, Sequence[str], None] = 'c250b0a6f9de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # First, so the links from counter_items below have something to point to.
    op.create_unique_constraint(op.f('uq_items_id_is_extra'), 'items', ['id', 'is_extra'])
    op.create_unique_constraint(op.f('uq_varieties_id_item_id'), 'varieties', ['id', 'item_id'])
    op.create_table('walk_ins',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('pickup_day_id', sa.Integer(), nullable=False),
    sa.Column('served_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('served_by_staff_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['pickup_day_id'], ['pickup_days.id'], name=op.f('fk_walk_ins_pickup_day_id')),
    sa.ForeignKeyConstraint(['served_by_staff_id'], ['staff.id'], name=op.f('fk_walk_ins_served_by_staff_id')),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], name=op.f('fk_walk_ins_student_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_walk_ins')),
    sa.UniqueConstraint('student_id', 'pickup_day_id', name=op.f('uq_walk_ins_student_id_pickup_day_id'))
    )
    op.create_table('counter_items',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('booking_id', sa.Integer(), nullable=True),
    sa.Column('walk_in_id', sa.Integer(), nullable=True),
    sa.Column('variety_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('is_extra', sa.Boolean(), nullable=False),
    sa.Column('quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint('NOT is_extra OR quantity = 1', name=op.f('ck_counter_items_one_of_an_extra')),
    sa.CheckConstraint('num_nonnulls(booking_id, walk_in_id) = 1', name=op.f('ck_counter_items_for_one_pickup')),
    sa.CheckConstraint('quantity >= 1', name=op.f('ck_counter_items_quantity_at_least_1')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_counter_items_booking_id'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id', 'is_extra'], ['items.id', 'items.is_extra'], name=op.f('fk_counter_items_item_id_is_extra')),
    sa.ForeignKeyConstraint(['variety_id', 'item_id'], ['varieties.id', 'varieties.item_id'], name=op.f('fk_counter_items_variety_id_item_id')),
    sa.ForeignKeyConstraint(['walk_in_id'], ['walk_ins.id'], name=op.f('fk_counter_items_walk_in_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_counter_items')),
    sa.UniqueConstraint('booking_id', 'variety_id', name=op.f('uq_counter_items_booking_id_variety_id')),
    sa.UniqueConstraint('walk_in_id', 'variety_id', name=op.f('uq_counter_items_walk_in_id_variety_id'))
    )
    op.create_index('uq_counter_items_one_extra_per_item_per_booking', 'counter_items', ['booking_id', 'item_id'], unique=True, postgresql_where=sa.text('is_extra'))
    op.create_index('uq_counter_items_one_extra_per_item_per_walk_in', 'counter_items', ['walk_in_id', 'item_id'], unique=True, postgresql_where=sa.text('is_extra'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_counter_items_one_extra_per_item_per_walk_in', table_name='counter_items', postgresql_where=sa.text('is_extra'))
    op.drop_index('uq_counter_items_one_extra_per_item_per_booking', table_name='counter_items', postgresql_where=sa.text('is_extra'))
    op.drop_table('counter_items')
    op.drop_table('walk_ins')
    # Last, once nothing links to them.
    op.drop_constraint(op.f('uq_varieties_id_item_id'), 'varieties', type_='unique')
    op.drop_constraint(op.f('uq_items_id_is_extra'), 'items', type_='unique')
