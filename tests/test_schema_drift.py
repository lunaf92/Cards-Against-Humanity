"""Schema-drift regression test: the migrated Postgres schema must match the ORM models.

Why this exists: every other test in this suite builds its schema straight from
`Base.metadata.create_all(...)` (see conftest.py's `test_db` fixture) — it never
runs Alembic migrations at all. That means a column declared on a model but
never added by a migration passes every other test silently, and only breaks
in a real, migrated Postgres database. That's exactly what happened with
`GameRound.created_at` and `Submission.created_at`: both were on the models
from the start, migration 001 never created them, and nothing caught it until
a real `docker compose up` + gameplay run hit an `UndefinedColumnError` (fixed
in alembic/versions/005_add_created_at_to_game_rounds_and_submissions.py).

This test is the regression guard for that class of bug. It needs a real,
already-migrated Postgres reachable at the `postgres` compose service — not
the sqlite-in-memory database the rest of the suite uses (.envs/.env.test
points there on purpose, for speed). Run it with:

    docker compose run --rm backend pytest tests/test_schema_drift.py -v

`docker compose run` starts `backend`'s dependency (the one-shot `migrate`
service) first, so the schema is already at head by the time this test
connects — no setup needed beyond having the stack buildable. It skips itself
if Postgres isn't reachable, so it never blocks the default sqlite-based
`pytest` run or requires the full stack to already be up.
"""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.models import Base

# Matches docker-compose.yml's postgres service credentials exactly. Deliberately
# not read from settings/DATABASE_URL: .env.test points at sqlite on purpose, and
# this check only means anything against the real, migrated Postgres database.
POSTGRES_URL = "postgresql+psycopg2://cah_user:cah_password@postgres:5432/cah_dev"


def test_migrated_schema_matches_models():
    """Fail loudly if a model column/table has no matching migration, or vice versa."""
    try:
        engine = create_engine(POSTGRES_URL)
        connection = engine.connect()
    except OperationalError:
        pytest.skip(
            "Postgres not reachable at postgres:5432 — run via "
            "`docker compose run --rm backend pytest tests/test_schema_drift.py -v`"
        )
        return

    try:
        context = MigrationContext.configure(connection)
        raw_diff = compare_metadata(context, Base.metadata)
    finally:
        connection.close()
        engine.dispose()

    # Alembic's index/unique-constraint autogenerate comparison is documented as
    # unreliable: a column declared `unique=True` can be implemented as either a
    # UniqueConstraint or a named Index depending on how the migration wrote it,
    # and compare_metadata often reports switching between those representations
    # as churn even when both enforce the identical guarantee. Filtering these op
    # types out is the standard tradeoff for a non-flaky drift check — it keeps
    # the test strict on what actually causes runtime crashes (missing/extra
    # tables and columns, wrong nullability, wrong type) without false-alarming
    # on cosmetic index/constraint naming differences.
    noisy_ops = {"add_index", "remove_index", "add_constraint", "remove_constraint"}

    def _op_name(item):
        # Same-column changes can arrive as a nested list of ops; check the first.
        return (item[0] if isinstance(item, list) else item)[0]

    diff = [item for item in raw_diff if _op_name(item) not in noisy_ops]

    assert not diff, (
        "Migrated schema and ORM models disagree — a migration is missing, stale, "
        f"or a model changed without one. Differences reported by Alembic: {diff}"
    )
