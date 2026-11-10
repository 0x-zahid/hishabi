"""Shared pytest fixtures.

Owner: Zahid. The tests run against **PostgreSQL**, not SQLite.

SQLite was originally used because it needs no server, but it silently
ignores ``SELECT ... FOR UPDATE``. The stock-movement endpoint relies on that
row lock to stop two concurrent movements from reading the same opening
balance and overwriting each other, so on SQLite the lock was never actually
exercised. Running against PostgreSQL means the lock is real.

The database used is ``TEST_DATABASE_URL`` from ``app.core.config`` (see
``.env``); it defaults to ``postgresql+psycopg://hishabi:password@localhost:5432/hishabi_test``.
Nothing here touches ``DATABASE_URL``, so the development database is safe.

Isolation strategy: the schema is created once per session, and every test
starts from a clean slate by truncating all tables and restarting the identity
sequences. That gives each test the same guarantee the old per-test
``create_all``/``drop_all`` cycle gave on SQLite, without paying for a schema
round-trip on every test.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import Base

# Importing the models package registers every table on ``Base.metadata``,
# which is what ``create_all`` and the truncation list are built from.
import app.models  # noqa: F401

TEST_DATABASE_URL = settings.TEST_DATABASE_URL


def _truncate_all(db: Session) -> None:
    """Empty every table and reset its identity sequence.

    ``RESTART IDENTITY`` matters: without it the ids keep climbing across
    tests, and a test that asserts on a specific id would depend on how many
    tests ran before it.
    """
    table_names = ", ".join(f'"{name}"' for name in reversed(Base.metadata.tables))
    db.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture(scope="session")
def postgres_engine():
    """Create the test schema once for the whole session."""
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, future=True)

    # Fail loudly and early if PostgreSQL is unreachable or the database does
    # not exist. A silent fallback to SQLite would defeat the whole point of
    # running these tests against PostgreSQL.
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as err:  # pragma: no cover - environment problem
        pytest.fail(
            f"Could not connect to the test database at {TEST_DATABASE_URL!r}: {err}. "
            "Create it with: createdb hishabi_test"
        )

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def test_db_session(postgres_engine) -> Session:
    """Return a clean PostgreSQL session for one test.

    This is the fixture every test module uses. The tables are truncated
    before and after the test, so no test can see another test's rows.
    """
    session_factory = sessionmaker(
        bind=postgres_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    db = session_factory()
    try:
        _truncate_all(db)
        yield db
    finally:
        db.rollback()
        db.close()
        _truncate_all(db)
