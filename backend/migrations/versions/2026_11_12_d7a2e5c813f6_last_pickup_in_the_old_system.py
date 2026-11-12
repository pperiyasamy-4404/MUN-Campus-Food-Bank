"""last pickup in the food bank's old system

Revision ID: d7a2e5c813f6
Revises: c4f19a27d3e5
Create Date: 2026-11-12 23:00:00.000000

Decided 12 Nov: when a volunteer gives a student a setup code, they can type
the student's last pickup from the food bank's old records. The pickup gap
counts from it too, so nobody gets a second bag within 30 days while the food
bank switches over to this system.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a2e5c813f6'
down_revision: Union[str, Sequence[str], None] = 'c4f19a27d3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('students', sa.Column('old_system_pickup_on', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('students', 'old_system_pickup_on')
