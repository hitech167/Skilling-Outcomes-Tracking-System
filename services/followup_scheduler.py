"""
Phase 5 — follow-up scheduling service.

Pure backend logic, no external services (no SMS/WhatsApp/email/Celery/
Redis — see Phase 5 spec). This module:

1. Generates the four standard follow-ups (30_DAY / 90_DAY / 6_MONTH /
   12_MONTH) for a completed training record, using real calendar date
   arithmetic (not "assume every month is 30 days").
2. Finds overdue and upcoming follow-ups.
3. Builds the counts used by the admin follow-up summary.

Kept intentionally simple: a couple of plain functions called directly
from routes/followup_tracking.py, no background workers.
"""

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import and_, case, func, text
from sqlalchemy.orm import Session

from database.models import FollowUp, Trainee, TrainingRecord

# (followup_type, days_offset, months_offset) — exactly one of the two
# offsets is used per row; the other is 0.
FOLLOWUP_SCHEDULE = (
    ("30_DAY", 30, 0),
    ("90_DAY", 90, 0),
    ("6_MONTH", 0, 6),
    ("12_MONTH", 0, 12),
)


def add_months(start: date, months: int) -> date:
    """
    Add calendar months to a date, clamping the day to the last valid day
    of the resulting month (e.g. Jan 31 + 1 month -> Feb 28/29, not an
    invalid Feb 31). This is the "proper calendar arithmetic" the spec
    asks for, without adding a new dependency (python-dateutil) to the
    project.
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = monthrange(year, month)[1]
    day = min(start.day, last_day_of_month)
    return date(year, month, day)


def generate_followup_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('followup_id_seq')")).scalar()
    return f"FUP{next_number:06d}"


def compute_followup_dates(completion_date: date) -> list[tuple[str, date]]:
    """Return [(followup_type, scheduled_date), ...] for one completion date."""
    dates = []
    for followup_type, days_offset, months_offset in FOLLOWUP_SCHEDULE:
        if months_offset:
            scheduled = add_months(completion_date, months_offset)
        else:
            scheduled = completion_date + timedelta(days=days_offset)
        dates.append((followup_type, scheduled))
    return dates


def generate_schedule_for_training(
    db: Session, trainee_pk_id: int, training_record_pk_id: int, completion_date: date
) -> list[FollowUp]:
    """
    Create the four follow-ups for a completed training, skipping any
    follow-up type that already exists for that training record so
    re-running this is always safe (no duplicates).

    Caller is responsible for the commit.
    """
    existing_types = {
        row[0]
        for row in db.query(FollowUp.followup_type)
        .filter(FollowUp.training_record_pk_id == training_record_pk_id)
        .all()
    }

    created: list[FollowUp] = []
    for followup_type, scheduled_date in compute_followup_dates(completion_date):
        if followup_type in existing_types:
            continue
        followup = FollowUp(
            followup_id=generate_followup_id(db),
            trainee_pk_id=trainee_pk_id,
            training_record_pk_id=training_record_pk_id,
            followup_type=followup_type,
            scheduled_date=scheduled_date,
            status="Scheduled",
        )
        db.add(followup)
        created.append(followup)

    return created


def _followup_list_query(db: Session):
    """
    Follow-ups with their trainee's and training's public IDs, fetched in
    ONE joined query (not one lookup per row), selecting only the columns
    the list responses use. Rows have: followup_id, followup_type,
    scheduled_date, status, trainee_id, training_id.
    """
    return db.query(
        FollowUp.followup_id,
        FollowUp.followup_type,
        FollowUp.scheduled_date,
        FollowUp.status,
        Trainee.trainee_id,
        TrainingRecord.record_id.label("training_id"),
    ).join(Trainee, Trainee.id == FollowUp.trainee_pk_id).join(
        TrainingRecord, TrainingRecord.id == FollowUp.training_record_pk_id
    )


def get_overdue_followups(db: Session) -> list:
    """Scheduled follow-ups whose scheduled_date has already passed."""
    today = date.today()
    return (
        _followup_list_query(db)
        .filter(FollowUp.status == "Scheduled", FollowUp.scheduled_date < today)
        .order_by(FollowUp.scheduled_date)
        .all()
    )


def get_upcoming_followups(db: Session, days: int) -> list:
    """Scheduled follow-ups due within the next `days` days (today included)."""
    today = date.today()
    horizon = today + timedelta(days=days)
    return (
        _followup_list_query(db)
        .filter(
            FollowUp.status == "Scheduled",
            FollowUp.scheduled_date >= today,
            FollowUp.scheduled_date <= horizon,
        )
        .order_by(FollowUp.scheduled_date)
        .all()
    )


def get_pending_followups(db: Session) -> list:
    """Scheduled follow-ups that are due (scheduled_date <= today)."""
    today = date.today()
    return (
        _followup_list_query(db)
        .filter(FollowUp.status == "Scheduled", FollowUp.scheduled_date <= today)
        .order_by(FollowUp.scheduled_date)
        .all()
    )


def get_admin_summary_counts(db: Session) -> dict:
    """Dynamically calculated counts for GET /api/followups/summary."""
    today = date.today()
    horizon_7 = today + timedelta(days=7)
    scheduled = FollowUp.status == "Scheduled"

    def count_where(*conditions):
        # COALESCE: SUM over an empty table is NULL, the count should be 0
        return func.coalesce(func.sum(case((and_(*conditions), 1), else_=0)), 0)

    # All seven counts in one pass over the table instead of seven COUNT queries
    row = db.query(
        func.count(FollowUp.id).label("total"),
        count_where(scheduled).label("scheduled"),
        count_where(FollowUp.status == "Completed").label("completed"),
        count_where(FollowUp.status == "Missed").label("missed"),
        count_where(FollowUp.status == "Not Reachable").label("not_reachable"),
        count_where(scheduled, FollowUp.scheduled_date < today).label("overdue"),
        count_where(
            scheduled, FollowUp.scheduled_date >= today, FollowUp.scheduled_date <= horizon_7
        ).label("upcoming_7_days"),
    ).one()

    return {key: int(value) for key, value in row._asdict().items()}
