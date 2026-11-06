"""check password and setup code hashes, log staff account changes

Revision ID: 8be36cf65217
Revises: 5275c044df61
Create Date: 2026-11-05 18:50:30.702393

Step 3, accounts and login:
- password hashes must be argon2, so a typed password can never be saved as text (P8)
- setup code hashes must look like an HMAC, so a code itself can never be saved
- the audit log can name the staff account an action was done to
- an empty staff_id in the audit log, or issued_by_staff_id on a setup code,
  means the setup script did it: the first coordinator (R3, R4)

Alembic doesn't notice new CHECK rules by itself, so those lines are written by hand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8be36cf65217'
down_revision: Union[str, Sequence[str], None] = '5275c044df61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('audit_log', sa.Column('affected_staff_id', sa.Integer(), nullable=True))
    op.alter_column('audit_log', 'staff_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.create_foreign_key(op.f('fk_audit_log_affected_staff_id'), 'audit_log', 'staff', ['affected_staff_id'], ['id'])
    op.alter_column('setup_codes', 'issued_by_staff_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    # Written by hand.
    op.create_check_constraint(op.f('ck_staff_password_hash_is_argon2'), 'staff', "password_hash LIKE '$argon2id$%'")
    op.create_check_constraint(op.f('ck_students_password_hash_is_argon2'), 'students', "password_hash LIKE '$argon2id$%'")
    op.create_check_constraint(op.f('ck_setup_codes_code_hash_looks_like_hmac'), 'setup_codes', "code_hash ~ '^[0-9a-f]{64}$'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_setup_codes_code_hash_looks_like_hmac'), 'setup_codes', type_='check')
    op.drop_constraint(op.f('ck_students_password_hash_is_argon2'), 'students', type_='check')
    op.drop_constraint(op.f('ck_staff_password_hash_is_argon2'), 'staff', type_='check')

    op.execute("DELETE FROM setup_codes WHERE issued_by_staff_id IS NULL")
    op.alter_column('setup_codes', 'issued_by_staff_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_constraint(op.f('fk_audit_log_affected_staff_id'), 'audit_log', type_='foreignkey')
    # Before this migration every log line needed a staff member, so the setup
    # script's lines can't be kept.
    op.execute("DELETE FROM audit_log WHERE staff_id IS NULL")
    op.alter_column('audit_log', 'staff_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('audit_log', 'affected_staff_id')
