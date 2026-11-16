"""Let deck owners delete cards that past rounds used.

game_rounds.black_card_id pointed at cards with no ON DELETE rule, so a black
card that had ever been drawn could not be deleted. Past rounds now keep a
null instead. Cards in a running game stay protected by the deck service.

Revision ID: 007
Revises: 006
Create Date: 2026-11-16 00:00:00.000000

"""
from alembic import op


revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Null out the prompt of past rounds when its card is deleted."""
    op.alter_column('game_rounds', 'black_card_id', nullable=True)
    op.drop_constraint('game_rounds_black_card_id_fkey', 'game_rounds', type_='foreignkey')
    op.create_foreign_key(
        'game_rounds_black_card_id_fkey', 'game_rounds', 'cards', ['black_card_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    """Restore the strict foreign key (fails if any round lost its card)."""
    op.drop_constraint('game_rounds_black_card_id_fkey', 'game_rounds', type_='foreignkey')
    op.create_foreign_key('game_rounds_black_card_id_fkey', 'game_rounds', 'cards', ['black_card_id'], ['id'])
    op.alter_column('game_rounds', 'black_card_id', nullable=False)
