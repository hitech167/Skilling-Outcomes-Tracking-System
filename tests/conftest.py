"""
Shared test setup.

By default every test runs against a throw-away in-memory SQLite
database, so running the suite never writes test rows into the
development database in DATABASE_URL. Set TEST_USE_REAL_DB=1 to run the
legacy test modules against DATABASE_URL instead (they only insert).

PostgreSQL sequences (SELECT nextval('...')) are emulated with a SQL
function registered on each SQLite connection.
"""

import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tests.auth_helpers  # noqa: F401  (sets test auth env vars first)

# Delivery providers must never be called from tests. Set to empty (not
# removed): the app calls load_dotenv() on import, which fills in any
# variable that is MISSING from .env — but never overrides one that is set.
for _var in ("SMTP_HOST", "SMS_WEBHOOK_URL", "FOLLOWUP_AUTO_DISPATCH_HOURS"):
    os.environ[_var] = ""

from database import models  # noqa: E402,F401  (register all tables)
from database.connection import Base, get_db  # noqa: E402
from main import app  # noqa: E402


def make_sqlite_session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    counters: dict = {}

    @event.listens_for(engine, "connect")
    def _register_nextval(dbapi_connection, _record):
        def nextval(name):
            counters[name] = counters.get(name, 0) + 1
            return counters[name]

        dbapi_connection.create_function("nextval", 1, nextval)

    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_db_with(session_factory):
    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_database():
    if os.getenv("TEST_USE_REAL_DB") == "1":
        yield
        return
    engine, factory = make_sqlite_session_factory()
    override_db_with(factory)
    yield
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture
def db_session_factory():
    """A brand-new empty database for one test; restores the previous override after."""
    previous = app.dependency_overrides.get(get_db)
    engine, Session = make_sqlite_session_factory()
    override_db_with(Session)
    yield Session
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous
    engine.dispose()


@pytest.fixture
def isolated_db(db_session_factory):
    """Alias used by the Phase 8 tests: a fresh, empty database for one test."""
    return db_session_factory
