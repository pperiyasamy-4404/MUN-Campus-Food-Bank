"""make the stock number optional, and add "few left"

Revision ID: a7c3e91f0b24
Revises: d19b90ad39dc
Create Date: 2026-11-12 10:00:00.000000

What-could-go-wrong problem 5 (decided 12 Nov): volunteers don't have time to
count every shelf. A variety's stock can now be empty, meaning "not counted,
in stock". A volunteer can mark food with no number as "few left". Food that
already has a number keeps it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91f0b24'
down_revision: Union[str, Sequence[str], None] = 'd19b90ad39dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # No default any more: food added without a number has none, like most food.
    op.alter_column('varieties', 'stock', existing_type=sa.Integer(), nullable=True, server_default=None, existing_server_default=sa.text('0'))
    op.add_column('varieties', sa.Column('few_left', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_check_constraint(
        op.f('ck_varieties_few_left_only_without_a_number'), 'varieties', 'NOT few_left OR stock IS NULL'
    )


def downgrade() -> None:
    """Downgrade schema. Food with no number becomes 0, out of stock, so nothing is over-promised."""
    op.drop_constraint(op.f('ck_varieties_few_left_only_without_a_number'), 'varieties', type_='check')
    op.drop_column('varieties', 'few_left')
    op.execute('UPDATE varieties SET stock = 0 WHERE stock IS NULL')
    op.alter_column('varieties', 'stock', existing_type=sa.Integer(), nullable=False, server_default=sa.text('0'))
