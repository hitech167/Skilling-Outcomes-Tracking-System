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

Performance: the database is usually remote, so a query per CSV row adds
up fast (a 5,000-row file used to cost ~4 lookups per row before any
writes). The lookups every row needs -- which trainee a row names, that
trainee's employers and latest training -- are loaded up front in a few
batched queries (SignalLookups) and kept in step as rows create records.
"""

import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from database.models import (
    EmployerVerification,
    EmploymentRecord,
    Outcome,
    Trainee,
    TraineeExternalId,
    TrainingRecord,
    WageHistory,
)
from routes.employer_verifications import generate_verification_id
from routes.employment import generate_employment_id
from routes.outcomes import generate_outcome_id
from routes.wage_history import generate_wage_record_id
MAX_ROWS = 5000
IN_BATCH = 1000  # values per IN (...) list
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


def _match_key(row: dict):
    """
    How a row identifies its trainee, in priority order: trainee_id, else
    phone (last 10 digits), else external_id as TYPE:VALUE. Returns
    (kind, value) or None. Only the first identifier present is used.
    """
    if row.get("trainee_id"):
        return ("trainee_id", row["trainee_id"])
    if row.get("phone"):
        return ("phone", re.sub(r"\D", "", row["phone"])[-10:])
    if row.get("external_id"):
        id_type, _, id_value = row["external_id"].partition(":")
        if id_value:
            # Same matching as identity_service.existing_owner: exact value, any-case type
            return ("external_id", (id_type.strip().lower(), id_value.strip()))
    return None


def _batches(values):
    values = list(values)
    for i in range(0, len(values), IN_BATCH):
        yield values[i : i + IN_BATCH]


class SignalLookups:
    """Everything the rows look up, loaded once for the whole file."""

    def __init__(self, db: Session, rows: list[dict]):
        keys = [k for k in (_match_key(r) for r in rows) if k is not None]
        wanted = defaultdict(set)
        for kind, value in keys:
            wanted[kind].add(value)

        self.by_key: dict = {}
        for batch in _batches(wanted["trainee_id"]):
            for t in db.query(Trainee).filter(Trainee.trainee_id.in_(batch)):
                self.by_key[("trainee_id", t.trainee_id)] = t
        for batch in _batches(wanted["phone"]):
            for t in db.query(Trainee).filter(Trainee.phone.in_(batch)):
                self.by_key[("phone", t.phone)] = t

        wanted_ext = wanted["external_id"]
        owner_pk = {}
        for batch in _batches({value for _type, value in wanted_ext}):
            links = (
                db.query(TraineeExternalId)
                .filter(TraineeExternalId.id_value.in_(batch))
                .order_by(TraineeExternalId.id)
            )
            for link in links:
                owner_pk.setdefault((link.id_type.lower(), link.id_value), link.trainee_pk_id)
        ext_trainees = {}
        for batch in _batches(set(owner_pk.values())):
            for t in db.query(Trainee).filter(Trainee.id.in_(batch)):
                ext_trainees[t.id] = t
        for key, pk in owner_pk.items():
            if key in wanted_ext and pk in ext_trainees:
                self.by_key[("external_id", key)] = ext_trainees[pk]

        trainee_pks = {t.id for t in self.by_key.values()}
        # trainee pk -> [(employment pk, company_name)], oldest first
        self.employments = defaultdict(list)
        # trainee pk -> latest training pk (latest end_date, undated last, then highest id)
        self.latest_training: dict = {}
        best: dict = {}
        for batch in _batches(trainee_pks):
            for e in (
                db.query(EmploymentRecord.id, EmploymentRecord.trainee_pk_id, EmploymentRecord.company_name)
                .filter(EmploymentRecord.trainee_pk_id.in_(batch))
                .order_by(EmploymentRecord.id)
            ):
                self.employments[e.trainee_pk_id].append((e.id, e.company_name))
            for tr in db.query(
                TrainingRecord.id, TrainingRecord.trainee_pk_id, TrainingRecord.end_date
            ).filter(TrainingRecord.trainee_pk_id.in_(batch)):
                rank = (tr.end_date is not None, tr.end_date or date.min, tr.id)
                if tr.trainee_pk_id not in best or rank > best[tr.trainee_pk_id]:
                    best[tr.trainee_pk_id] = rank
                    self.latest_training[tr.trainee_pk_id] = tr.id

    def trainee_for(self, row: dict) -> Trainee | None:
        key = _match_key(row)
        return self.by_key.get(key) if key is not None else None


def _same_name(a: str | None, b: str | None) -> bool:
    return bool(a and b) and " ".join(a.lower().split()) == " ".join(b.lower().split())


def process_row(
    db: Session, row: dict, source: str, dry_run: bool, lookups: SignalLookups
) -> tuple[str, str | None]:
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

    trainee = lookups.trainee_for(row)
    if trainee is None:
        return "trainee_not_found", None
    if not trainee.consent_given:
        return "no_consent", None

    existing = [
        employment_pk
        for employment_pk, company_name in lookups.employments[trainee.id]
        if _same_name(company_name, employer)
    ]
    reference = row.get("reference") or "no reference"
    note = f"Confirmed by external source {source} ({reference})"

    if existing:
        pending = (
            db.query(EmployerVerification)
            .filter(
                EmployerVerification.employment_pk_id == existing[0],
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

    training_pk = lookups.latest_training.get(trainee.id)
    if training_pk is None:
        return "no_training", None
    if dry_run:
        return "created", None

    today = date.today()
    outcome = Outcome(
        outcome_id=generate_outcome_id(db),
        trainee_pk_id=trainee.id,
        training_record_pk_id=training_pk,
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
    # Later rows in this file for the same trainee + employer see this job
    lookups.employments[trainee.id].append((employment.id, employer))
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
    lookups = SignalLookups(db, rows)
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        result, detail = process_row(db, row, source, dry_run, lookups)
        summary[result] += 1
        if result in ("invalid", "trainee_not_found", "no_training") and len(summary["problems"]) < 50:
            summary["problems"].append({"row": number, "result": result, "detail": detail})
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return summary
