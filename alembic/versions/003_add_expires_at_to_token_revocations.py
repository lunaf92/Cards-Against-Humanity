"""Add expires_at column to token_revocations table.

Revision ID: 003
Revises: 002
Create Date: 2026-04-26 09:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add token expiration timestamp used for revocation cleanup."""
    op.add_column("token_revocations", sa.Column("expires_at", sa.DateTime(), nullable=True))

    # Backfill existing records safely before enforcing NOT NULL.
    op.execute("UPDATE token_revocations SET expires_at = revoked_at WHERE expires_at IS NULL")

    op.alter_column("token_revocations", "expires_at", nullable=False)


def downgrade() -> None:
    """Drop token expiration timestamp column."""
    op.drop_column("token_revocations", "expires_at")
