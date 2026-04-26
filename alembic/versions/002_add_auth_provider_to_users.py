"""Add auth_provider column to users table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-26 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add optional auth provider field for future social login support."""
    op.add_column("users", sa.Column("auth_provider", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove auth provider field from users table."""
    op.drop_column("users", "auth_provider")
