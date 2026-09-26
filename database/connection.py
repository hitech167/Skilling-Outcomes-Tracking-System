"""
Database connection setup.

Reads DATABASE_URL from the .env file and creates the SQLAlchemy engine,
session factory and declarative Base used by the rest of the app.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Load variables from Backend/.env into the environment
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Fail early and clearly if the connection string is missing
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and put your "
        "PostgreSQL/Supabase connection string in it."
    )

# Supabase sometimes gives a URL starting with "postgres://".
# SQLAlchemy expects "postgresql://", so we normalise it here.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Be explicit about the driver (psycopg2)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg2://", 1
    )

# pool_pre_ping=True makes SQLAlchemy check a connection before using it.
# This matters for Supabase, which closes idle connections.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()

# Sequences behind the public IDs (TRN000001, OUT000001, ...). They are not
# tied to a table, so dropping the tables does not reset them; see
# scripts/reset_database.py.
ID_SEQUENCES = (
    "trainee_id_seq",
    "training_record_id_seq",
    "outcome_id_seq",
    "employment_id_seq",
    "self_employment_id_seq",
    "apprenticeship_id_seq",
    "non_placement_id_seq",
    "followup_id_seq",
    "employer_verification_id_seq",
    "wage_history_id_seq",
    "employment_status_id_seq",
    # Phase 5 — follow-up attempts and outcome-update snapshots
    "followup_attempt_id_seq",
    "followup_outcome_update_id_seq",
    "notification_id_seq",
)


def get_db():
    """FastAPI dependency: give a DB session to a route, then close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Create the tables and the ID sequences if they do not exist yet.

    Called once on application startup. No migration tool needed so far.
    """
    # Import here so the models are registered on Base before create_all()
    from database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # PostgreSQL sequences give us safe, gap-free-ish numbering even when
    # two requests happen at the same moment.
    with engine.begin() as conn:
        for sequence in ID_SEQUENCES:
            conn.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {sequence} START 1"))

        # Phase 8 — additive, nullable columns on an existing table.
        # create_all() never alters existing tables, so add them here.
        # ADD COLUMN IF NOT EXISTS is non-destructive: existing rows keep
        # all their data and get NULL in the new columns.
        conn.execute(
            text(
                "ALTER TABLE training_records "
                "ADD COLUMN IF NOT EXISTS program_name VARCHAR(200)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE training_records "
                "ADD COLUMN IF NOT EXISTS assessment_status VARCHAR(10)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_training_records_program_name "
                "ON training_records (program_name)"
            )
        )
