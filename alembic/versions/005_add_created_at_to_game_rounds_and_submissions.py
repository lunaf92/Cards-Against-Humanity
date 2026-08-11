"""Add missing created_at columns to game_rounds and submissions.

The GameRound and Submission ORM models both declare a created_at column
(app/models/game_round.py, app/models/submission.py), but migration 001 never
added it to either table's DDL — every other timestamped table (users, cards,
rooms) got it, these two didn't. Any SELECT that loads a full GameRound or
Submission row fails immediately with UndefinedColumnError, which breaks the
whole gameplay loop (build_game_state, submit_cards, pick_winner) on any
freshly migrated database. Both tables are empty on any install that hits
this, since a round can't complete without them, so no backfill is needed.

Revision ID: 005
Revises: 004
Create Date: 2026-08-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add created_at to game_rounds and submissions, matching the ORM models."""
    op.add_column('game_rounds', sa.Column('created_at', sa.DateTime(), nullable=False))
    op.add_column('submissions', sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade() -> None:
    """Drop created_at from game_rounds and submissions."""
    op.drop_column('submissions', 'created_at')
    op.drop_column('game_rounds', 'created_at')
