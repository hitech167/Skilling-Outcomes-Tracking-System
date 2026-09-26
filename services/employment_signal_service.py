"""
Import of employment signals from an outside source (EPFO / ESIC extract,
a job-portal or state placement-system export, an employer's HR sheet).

Each row names a trainee (trainee_id, phone, or an external ID as
TYPE:VALUE) and an employer. For a matched, consenting trainee we record
an Employed outcome on their latest training, an employment record, an
optional wage point and an employer verification marked Verified by
"Document" - the outside source is the evidence. If the trainee already
has that employer on record, nothing is duplicated; a Pending
verification for it is just resolved.

Rows are independent: a bad row is reported, not fatal. With dry_run the
whole file is checked and nothing is written.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from database.models import (
    EmployerVerification,
    EmploymentRecord,
    Outcome,
    Trainee,
    TrainingRecord,
    WageHistory,
)
from routes.employer_verifications import generate_verification_id
from routes.employment import generate_employment_id
from routes.outcomes import generate_outcome_id
from routes.wage_history import generate_wage_record_id
from services import identity_service

MAX_ROWS = 5000
REQUIRED_HEADERS = {"employer_name", "start_date"}
MATCH_HEADERS = {"trainee_id", "phone", "external_id"}


class SignalFileError(ValueError):
    pass


def parse_csv(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SignalFileError("File must be UTF-8 encoded CSV.")
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not REQUIRED_HEADERS <= headers or not headers & MATCH_HEADERS:
        raise SignalFileError(
            "CSV needs columns employer_name, start_date and at least one of "
            "trainee_id, phone, external_id."
        )
    rows = []
    for row in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
        if len(rows) > MAX_ROWS:
            raise SignalFileError(f"At most {MAX_ROWS} rows per file.")
    return rows


def _find_trainee(db: Session, row: dict) -> Trainee | None:
    if row.get("trainee_id"):
        return db.query(Trainee).filter(Trainee.trainee_id == row["trainee_id"]).first()
    if row.get("phone"):
        digits = re.sub(r"\D", "", row["phone"])[-10:]
        return db.query(Trainee).filter(Trainee.phone == digits).first()
    if row.get("external_id"):
        id_type, _, id_value = row["external_id"].partition(":")
        if id_value:
            return identity_service.existing_owner(db, id_type.strip(), id_value.strip())
    return None


def _same_name(a: str | None, b: str | None) -> bool:
    return bool(a and b) and " ".join(a.lower().split()) == " ".join(b.lower().split())


def process_row(db: Session, row: dict, source: str, dry_run: bool) -> tuple[str, str | None]:
    """Return (result, detail). Results: created, already_recorded, verified_existing,
    trainee_not_found, no_consent, no_training, invalid."""
    employer = row.get("employer_name", "")
    if not employer:
        return "invalid", "employer_name is empty"
    try:
        start = datetime.strptime(row.get("start_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return "invalid", "start_date must be YYYY-MM-DD"
    salary = None
    if row.get("monthly_salary"):
        try:
            salary = Decimal(row["monthly_salary"])
        except InvalidOperation:
            return "invalid", "monthly_salary is not a number"
        if salary <= 0:
            return "invalid", "monthly_salary must be positive"
    if start > date.today():
        return "invalid", "start_date is in the future"

    trainee = _find_trainee(db, row)
    if trainee is None:
        return "trainee_not_found", None
    if not trainee.consent_given:
        return "no_consent", None

    existing = [
        e for e in db.query(EmploymentRecord).filter(EmploymentRecord.trainee_pk_id == trainee.id)
        if _same_name(e.company_name, employer)
    ]
    reference = row.get("reference") or "no reference"
    note = f"Confirmed by external source {source} ({reference})"

    if existing:
        pending = (
            db.query(EmployerVerification)
            .filter(
                EmployerVerification.employment_pk_id == existing[0].id,
                EmployerVerification.verification_status == "Pending",
            )
            .all()
        )
        if not pending:
            return "already_recorded", None
        if not dry_run:
            for verification in pending:
                verification.verification_status = "Verified"
                verification.verification_method = "Document"
                verification.verified_date = date.today()
                verification.verified_by = source
                verification.verification_notes = note
        return "verified_existing", None

    training = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.trainee_pk_id == trainee.id)
        .order_by(TrainingRecord.end_date.desc().nullslast(), TrainingRecord.id.desc())
        .first()
    )
    if training is None:
        return "no_training", None
    if dry_run:
        return "created", None

    today = date.today()
    outcome = Outcome(
        outcome_id=generate_outcome_id(db),
        trainee_pk_id=trainee.id,
        training_record_pk_id=training.id,
        outcome_type="Employed",
        status_date=today,
        notes=note,
    )
    db.add(outcome)
    db.flush()
    employment = EmploymentRecord(
        employment_id=generate_employment_id(db),
        outcome_pk_id=outcome.id,
        trainee_pk_id=trainee.id,
        company_name=employer,
        job_role=row.get("job_role") or "Not specified",
        joining_date=start,
        salary=salary,
        employment_status="Active",
    )
    db.add(employment)
    db.flush()
    if salary is not None:
        db.add(
            WageHistory(
                wage_record_id=generate_wage_record_id(db),
                employment_pk_id=employment.id,
                trainee_pk_id=trainee.id,
                salary=salary,
                salary_period="Monthly",
                effective_date=today,
                source="Document",
                verification_status="Verified",
                notes=note,
            )
        )
    db.add(
        EmployerVerification(
            verification_id=generate_verification_id(db),
            employment_pk_id=employment.id,
            trainee_pk_id=trainee.id,
            employer_name=employer,
            verification_status="Verified",
            verification_method="Document",
            verified_date=today,
            verified_by=source,
            verification_notes=note,
        )
    )
    return "created", None


def import_signals(db: Session, rows: list[dict], source: str, dry_run: bool) -> dict:
    summary = {
        "source": source,
        "dry_run": dry_run,
        "rows": len(rows),
        "created": 0,
        "verified_existing": 0,
        "already_recorded": 0,
        "trainee_not_found": 0,
        "no_consent": 0,
        "no_training": 0,
        "invalid": 0,
        "problems": [],
    }
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        result, detail = process_row(db, row, source, dry_run)
        summary[result] += 1
        if result in ("invalid", "trainee_not_found", "no_training") and len(summary["problems"]) < 50:
            summary["problems"].append({"row": number, "result": result, "detail": detail})
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return summary
