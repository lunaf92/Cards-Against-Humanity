"""Add decks: built-in packs and user-made decks, their co-editors, and room deck choices.

Cards get a deck_id. Built-in cards are tagged by rerunning the seeder
(python -m scripts.seed_cards), which creates one deck per pack and matches
existing cards by text. Custom cards that users already made are moved into a
private "My cards" deck per owner here, so nothing is left without a deck
except built-in cards the seeder no longer ships.

Revision ID: 006
Revises: 005
Create Date: 2026-11-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    """Create deck tables and link cards to decks."""
    op.create_table(
        'decks',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('slug', sa.String(64), nullable=True, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('owner_id', UUID, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('share_code', sa.String(12), nullable=True, unique=True),
        sa.Column('copied_from_id', UUID, sa.ForeignKey('decks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_decks_owner_id', 'decks', ['owner_id'])

    op.create_table(
        'deck_members',
        sa.Column('deck_id', UUID, sa.ForeignKey('decks.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', UUID, sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_deck_members_user_id', 'deck_members', ['user_id'])

    op.create_table(
        'room_decks',
        sa.Column('room_id', UUID, sa.ForeignKey('rooms.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('deck_id', UUID, sa.ForeignKey('decks.id', ondelete='CASCADE'), primary_key=True),
    )

    op.add_column('cards', sa.Column('deck_id', UUID, nullable=True))
    op.create_foreign_key('fk_cards_deck_id', 'cards', 'decks', ['deck_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_cards_deck_id', 'cards', ['deck_id'])

    # Existing custom cards go into one private "My cards" deck per owner.
    op.execute(
        """
        INSERT INTO decks (id, name, language, owner_id, is_public, created_at, updated_at)
        SELECT gen_random_uuid(), 'My cards', 'en', owner_id, false, now(), now()
        FROM (SELECT DISTINCT owner_id FROM cards WHERE owner_id IS NOT NULL AND is_default = false) owners
        """
    )
    op.execute(
        """
        UPDATE cards SET deck_id = decks.id
        FROM decks
        WHERE cards.owner_id = decks.owner_id AND cards.is_default = false AND cards.deck_id IS NULL
        """
    )


def downgrade() -> None:
    """Drop deck tables and the card link."""
    op.drop_index('ix_cards_deck_id', table_name='cards')
    op.drop_constraint('fk_cards_deck_id', 'cards', type_='foreignkey')
    op.drop_column('cards', 'deck_id')
    op.drop_table('room_decks')
    op.drop_index('ix_deck_members_user_id', table_name='deck_members')
    op.drop_table('deck_members')
    op.drop_index('ix_decks_owner_id', table_name='decks')
    op.drop_table('decks')
