"""add a photo for each item

Revision ID: 22ef6889a3d0
Revises: 8ed315f3aef8
Create Date: 2026-11-07 13:25:13.562347


Each item can have one photo, shown to students on the food cards. A table of
its own, so reading the food list never loads the pictures. CHECK rules made by
Alembic from the table class: the type must be JPEG, PNG or WebP, and the
photo at most 2 MB.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22ef6889a3d0'
down_revision: Union[str, Sequence[str], None] = '8ed315f3aef8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('item_photos',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('content_type', sa.Text(), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("content_type IN ('image/jpeg', 'image/png', 'image/webp')", name=op.f('ck_item_photos_content_type_is_known')),
    sa.CheckConstraint('octet_length(data) BETWEEN 1 AND 2097152', name=op.f('ck_item_photos_small_enough')),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_item_photos_item_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_item_photos'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('item_photos')
