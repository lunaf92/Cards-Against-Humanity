"""Initial migration: create all base tables with language support for cards.

Revision ID: 001
Revises: 
Create Date: 2026-04-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all base tables for the application."""
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(50), nullable=False, unique=True),
        sa.Column('email', sa.String(255), nullable=True, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create cards table with language support
    op.create_table(
        'cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.Enum('black', 'white', name='card_type'), nullable=False),
        sa.Column('text', sa.String(500), nullable=False),
        sa.Column('pick', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create rooms table
    op.create_table(
        'rooms',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(6), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('room_kind', sa.Enum('private', 'random', name='room_kind'), nullable=False),
        sa.Column('status', sa.Enum('lobby', 'matchmaking_lobby', 'in_progress', 'finished', name='room_status'), nullable=False),
        sa.Column('max_players', sa.Integer(), nullable=False),
        sa.Column('winning_score', sa.Integer(), nullable=False),
        sa.Column('round_timer_seconds', sa.Integer(), nullable=False),
        sa.Column('card_pool_mode', sa.Enum('default_only', 'host_custom_only', 'host_custom_mixed', 'all_custom_only', 'all_custom_mixed', name='card_pool_mode'), nullable=False),
        sa.Column('matchmaking_fill_expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create room_players table
    op.create_table(
        'room_players',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('room_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('join_order', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_connected', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create game_rounds table
    op.create_table(
        'game_rounds',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('room_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('czar_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('black_card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('waiting', 'judging', 'complete', name='round_status'), nullable=False),
        sa.ForeignKeyConstraint(['black_card_id'], ['cards.id'], ),
        sa.ForeignKeyConstraint(['czar_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create submissions table
    op.create_table(
        'submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('round_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('white_card_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('is_winner', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['round_id'], ['game_rounds.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create token_revocations table
    op.create_table(
        'token_revocations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_jti', sa.String(500), nullable=False, unique=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indices
    op.create_index(op.f('ix_cards_owner_id'), 'cards', ['owner_id'], unique=False)
    op.create_index(op.f('ix_rooms_host_id'), 'rooms', ['host_id'], unique=False)
    op.create_index(op.f('ix_room_players_room_id'), 'room_players', ['room_id'], unique=False)
    op.create_index(op.f('ix_game_rounds_room_id'), 'game_rounds', ['room_id'], unique=False)
    op.create_index(op.f('ix_submissions_round_id'), 'submissions', ['round_id'], unique=False)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index(op.f('ix_submissions_round_id'), table_name='submissions')
    op.drop_index(op.f('ix_game_rounds_room_id'), table_name='game_rounds')
    op.drop_index(op.f('ix_room_players_room_id'), table_name='room_players')
    op.drop_index(op.f('ix_rooms_host_id'), table_name='rooms')
    op.drop_index(op.f('ix_cards_owner_id'), table_name='cards')
    op.drop_table('token_revocations')
    op.drop_table('submissions')
    op.drop_table('game_rounds')
    op.drop_table('room_players')
    op.drop_table('rooms')
    op.drop_table('cards')
    op.drop_table('users')

