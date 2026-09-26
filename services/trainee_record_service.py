"""
The trainee's own record, as shown on their profile link.

The link is a bearer secret (anyone holding it can open it), so this is a
deliberately limited view: phone and email are masked, and date of birth,
wages / income and internal verification details are left out. It shows what
is held about the trainee - training, outcomes, follow-up status - and
their consent history.
"""

from typing import Optional

from sqlalchemy.orm import Session

from database.models import (
    ApprenticeshipRecord,
    EmployerVerification,
    EmploymentRecord,
    EmploymentStatusHistory,
    FollowUp,
    Outcome,
    SelfEmploymentRecord,
    Trainee,
    TraineeConsentHistory,
    TrainingRecord,
)


def mask_phone(phone: str) -> str:
    return f"{phone[:2]}{'•' * max(len(phone) - 4, 0)}{phone[-2:]}" if len(phone) > 4 else "••••"


def mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'•' * 3}@{domain}"


def build_record(db: Session, trainee: Trainee) -> dict:
    trainings = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.trainee_pk_id == trainee.id)
        .order_by(TrainingRecord.start_date)
        .all()
    )
    followups = (
        db.query(FollowUp)
        .filter(FollowUp.trainee_pk_id == trainee.id)
        .order_by(FollowUp.scheduled_date)
        .all()
    )
    outcomes = (
        db.query(Outcome)
        .filter(Outcome.trainee_pk_id == trainee.id)
        .order_by(Outcome.status_date)
        .all()
    )
    course_of = {t.id: t for t in trainings}

    jobs = []
    employments = (
        db.query(EmploymentRecord)
        .filter(EmploymentRecord.trainee_pk_id == trainee.id)
        .order_by(EmploymentRecord.joining_date, EmploymentRecord.id)
        .all()
    )
    ids = [e.id for e in employments]
    # Latest verification and latest status of every job, one query each (not one per job)
    latest_verification, latest_status = {}, {}
    if ids:
        for employment_pk_id, verification_status in (
            db.query(EmployerVerification.employment_pk_id, EmployerVerification.verification_status)
            .filter(EmployerVerification.employment_pk_id.in_(ids))
            .order_by(EmployerVerification.id)
        ):
            latest_verification[employment_pk_id] = verification_status  # ascending: last wins
        # Current status = the latest status-history entry, as staff see it
        # (employment_records.employment_status is only the status at the start)
        for employment_pk_id, status_value in (
            db.query(EmploymentStatusHistory.employment_pk_id, EmploymentStatusHistory.employment_status)
            .filter(EmploymentStatusHistory.employment_pk_id.in_(ids))
            .order_by(EmploymentStatusHistory.status_date, EmploymentStatusHistory.id)
        ):
            latest_status[employment_pk_id] = status_value  # ascending: last wins
    for employment in employments:
        jobs.append(
            {
                "type": "Employed",
                "organisation": employment.company_name,
                "role": employment.job_role,
                "since": employment.joining_date,
                "status": latest_status.get(employment.id, employment.employment_status),
                "employer_confirmation": latest_verification.get(employment.id),
            }
        )
    for record in (
        db.query(SelfEmploymentRecord)
        .filter(SelfEmploymentRecord.trainee_pk_id == trainee.id)
        .order_by(SelfEmploymentRecord.start_date, SelfEmploymentRecord.id)
    ):
        jobs.append(
            {"type": "Self-employed", "organisation": record.business_name, "role": record.business_type,
             "since": record.start_date, "status": None, "employer_confirmation": None}
        )
    for record in (
        db.query(ApprenticeshipRecord)
        .filter(ApprenticeshipRecord.trainee_pk_id == trainee.id)
        .order_by(ApprenticeshipRecord.start_date, ApprenticeshipRecord.id)
    ):
        jobs.append(
            {"type": "Apprenticeship", "organisation": record.organization_name, "role": record.role,
             "since": record.start_date, "status": None, "employer_confirmation": None}
        )
    # Work history in date order (a stable sort keeps same-day jobs in the order above)
    jobs.sort(key=lambda job: job["since"])

    consent_history = (
        db.query(TraineeConsentHistory)
        .filter(TraineeConsentHistory.trainee_pk_id == trainee.id)
        .order_by(TraineeConsentHistory.id.desc())
        .all()
    )

    return {
        "profile": {
            "trainee_id": trainee.trainee_id,
            "full_name": trainee.full_name,
            "gender": trainee.gender,
            "district": trainee.district,
            "current_location": trainee.current_location,
            "phone": mask_phone(trainee.phone),
            "email": mask_email(trainee.email),
            "preferred_contact": trainee.preferred_contact,
        },
        "consent": {
            "given": trainee.consent_given,
            "since": trainee.consent_date,
            "history": [
                {
                    "consent_given": h.consent_given,
                    "when": h.changed_at,
                    "how": h.method,
                    "recorded_by": "You" if h.source == "self" else "Programme staff",
                }
                for h in consent_history
            ],
        },
        "training": [
            {
                "course": t.course_name,
                "provider": t.provider_name,
                "start_date": t.start_date,
                "end_date": t.end_date,
                "status": t.status,
                "certificate_issued": t.certification_issued,
            }
            for t in trainings
        ],
        "outcomes": [
            {
                "outcome": o.outcome_type,
                "date": o.status_date,
                "course": course_of[o.training_record_pk_id].course_name
                if o.training_record_pk_id in course_of
                else None,
            }
            for o in outcomes
        ],
        "work": jobs,
        "follow_ups": [
            {"type": f.followup_type, "due": f.scheduled_date, "status": f.status} for f in followups
        ],
    }
