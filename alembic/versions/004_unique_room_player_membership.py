"""Add unique constraint on room_players (room_id, player_id).

Membership checks are check-then-insert in the service layer; this constraint
makes the database the authority under concurrent joins.

Revision ID: 004
Revises: 003
Create Date: 2026-07-15 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add unique membership constraint."""
    op.create_unique_constraint(
        'uq_room_players_room_player',
        'room_players',
        ['room_id', 'player_id'],
    )


def downgrade() -> None:
    """Drop unique membership constraint."""
    op.drop_constraint('uq_room_players_room_player', 'room_players', type_='unique')
