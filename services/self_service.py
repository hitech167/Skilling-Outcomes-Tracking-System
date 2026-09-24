"""
Low-burden data capture without logins.

Trainee self-report: one signed link per follow-up. Submitting it
records, in one transaction, exactly what an admin would otherwise key
in by hand: a follow-up outcome update, an Outcome, the matching detail
record (employment / self-employment / apprenticeship / non-placement),
a Trainee-sourced unverified wage for jobs, a Pending employer
verification for jobs, a successful contact attempt, and marks the
follow-up Completed. Self-reported jobs are therefore visible as
"awaiting employer validation", never silently treated as verified.
If the trainee reports the SAME employer / business / apprenticeship
they already have on record, that record is extended (new wage point,
status back to Active if needed) instead of duplicated.

Employer confirmation: one signed link per verification request.
Submitting it resolves that Pending verification (Verified / Rejected)
and, if given, adds an Employer-sourced verified wage and a status
history row.

Both links are single-use: once the follow-up is no longer Scheduled
(or the verification no longer Pending) the link returns 409.
"""

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import (
    ApprenticeshipRecord,
    EmployerVerification,
    EmploymentRecord,
    EmploymentStatusHistory,
    FollowUp,
    FollowUpAttempt,
    FollowUpOutcomeUpdate,
    NonPlacementRecord,
    Outcome,
    SelfEmploymentRecord,
    Trainee,
    TrainingRecord,
    WageHistory,
)
from routes.apprenticeship import generate_apprenticeship_id
from routes.employer_verifications import generate_verification_id
from routes.employment import generate_employment_id
from routes.employment_status import generate_status_record_id
from routes.followup_tracking import generate_attempt_id, generate_outcome_update_id
from routes.non_placement import generate_non_placement_id
from routes.outcomes import generate_outcome_id
from routes.self_employment import generate_self_employment_id
from routes.wage_history import generate_wage_record_id
from schemas.self_service import EmployerVerifySubmission, SelfReportSubmission
from services.analytics_service import monthly_equivalent


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is invalid or has expired.")


# ---------------------------------------------------------------------
# Trainee self-report
# ---------------------------------------------------------------------


def load_followup_context(db: Session, followup_id: str):
    followup = db.query(FollowUp).filter(FollowUp.followup_id == followup_id).first()
    if followup is None:
        raise _not_found()
    trainee = db.query(Trainee).filter(Trainee.id == followup.trainee_pk_id).one()
    training = db.query(TrainingRecord).filter(TrainingRecord.id == followup.training_record_pk_id).one()
    return followup, trainee, training


def submit_self_report(db: Session, followup_id: str, report: SelfReportSubmission) -> None:
    followup, trainee, training = load_followup_context(db, followup_id)
    # Lock the row and RE-READ it (populate_existing): a second submit that
    # was waiting on the lock must see the status the first one committed,
    # not the stale copy loaded above.
    followup = (
        db.query(FollowUp)
        .filter(FollowUp.id == followup.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if followup.status != "Scheduled":
        raise _conflict("This check-in has already been completed. Thank you!")
    if not trainee.consent_given:
        raise _conflict("Consent for follow-up has been withdrawn, so no update can be recorded.")

    today = date.today()
    start = report.start_date or today
    source_note = f"Self-reported by trainee via follow-up link ({followup.followup_id})"

    db.add(
        FollowUpOutcomeUpdate(
            update_id=generate_outcome_update_id(db),
            followup_pk_id=followup.id,
            trainee_pk_id=trainee.id,
            employment_status=report.outcome_type,
            training_relevance=report.training_relevance,
            skill_gap=report.skill_gap,
            additional_training_needed=report.additional_training_needed,
            unemployment_reason_category=report.unemployment_reason if report.outcome_type == "Unemployed" else None,
            notes=report.notes,
        )
    )

    outcome = Outcome(
        outcome_id=generate_outcome_id(db),
        trainee_pk_id=trainee.id,
        training_record_pk_id=training.id,
        outcome_type=report.outcome_type,
        status_date=today,
        notes=source_note,
    )
    db.add(outcome)
    db.flush()

    existing = _existing_placement(db, trainee.id, report)
    if existing is not None:
        # Same job / business / apprenticeship as last time: extend its
        # history instead of creating a duplicate record.
        if isinstance(existing, EmploymentRecord):
            _update_existing_employment(db, existing, trainee, report, today, source_note)
    elif report.outcome_type == "Employed":
        employment = EmploymentRecord(
            employment_id=generate_employment_id(db),
            outcome_pk_id=outcome.id,
            trainee_pk_id=trainee.id,
            company_name=report.organisation_name,
            job_role=report.role,
            joining_date=start,
            salary=report.monthly_income,
            employment_status="Active",
        )
        db.add(employment)
        db.flush()
        if report.monthly_income is not None:
            db.add(
                WageHistory(
                    wage_record_id=generate_wage_record_id(db),
                    employment_pk_id=employment.id,
                    trainee_pk_id=trainee.id,
                    salary=report.monthly_income,
                    salary_period="Monthly",
                    effective_date=today,
                    source="Trainee",
                    verification_status="Unverified",
                    notes=source_note,
                )
            )
        db.add(
            EmployerVerification(
                verification_id=generate_verification_id(db),
                employment_pk_id=employment.id,
                trainee_pk_id=trainee.id,
                employer_name=report.organisation_name,
                verification_status="Pending",
                verification_method="Trainee Confirmation",
                verification_notes="Self-reported by trainee; awaiting employer validation.",
            )
        )
    elif report.outcome_type == "Self-employed":
        db.add(
            SelfEmploymentRecord(
                self_employment_id=generate_self_employment_id(db),
                outcome_pk_id=outcome.id,
                trainee_pk_id=trainee.id,
                business_name=report.organisation_name,
                business_type=report.role,
                start_date=start,
                monthly_income=report.monthly_income,
            )
        )
    elif report.outcome_type == "Apprenticeship":
        db.add(
            ApprenticeshipRecord(
                apprenticeship_id=generate_apprenticeship_id(db),
                outcome_pk_id=outcome.id,
                trainee_pk_id=trainee.id,
                organization_name=report.organisation_name,
                role=report.role,
                start_date=start,
                monthly_stipend=report.monthly_income,
            )
        )
    elif report.outcome_type == "Unemployed" and report.unemployment_reason:
        db.add(
            NonPlacementRecord(
                non_placement_id=generate_non_placement_id(db),
                outcome_pk_id=outcome.id,
                trainee_pk_id=trainee.id,
                reason_category=report.unemployment_reason,
                reason_details=report.notes,
            )
        )

    db.add(
        FollowUpAttempt(
            attempt_id=generate_attempt_id(db),
            followup_pk_id=followup.id,
            attempt_date=today,
            contact_method="Other",
            attempt_status="Successful",
            notes="Trainee responded through the self-report link",
        )
    )
    followup.status = "Completed"
    followup.completed_date = max(today, followup.scheduled_date)
    followup.outcome_pk_id = outcome.id
    db.commit()


def _same_name(a: str | None, b: str | None) -> bool:
    return bool(a and b) and " ".join(a.lower().split()) == " ".join(b.lower().split())


def _existing_placement(db: Session, trainee_pk_id: int, report: SelfReportSubmission):
    """The trainee's existing job / business / apprenticeship with the same name, if any."""
    model, name_field, order_field = {
        "Employed": (EmploymentRecord, "company_name", "joining_date"),
        "Self-employed": (SelfEmploymentRecord, "business_name", "start_date"),
        "Apprenticeship": (ApprenticeshipRecord, "organization_name", "start_date"),
    }.get(report.outcome_type, (None, None, None))
    if model is None:
        return None
    rows = (
        db.query(model)
        .filter(model.trainee_pk_id == trainee_pk_id)
        .order_by(getattr(model, order_field).desc(), model.id.desc())
        .all()
    )
    return next((r for r in rows if _same_name(getattr(r, name_field), report.organisation_name)), None)


def _update_existing_employment(db, employment, trainee, report, today, source_note):
    """Add a new wage point / status change to a job the trainee already reported."""
    if report.monthly_income is not None:
        latest_wage = (
            db.query(WageHistory)
            .filter(WageHistory.employment_pk_id == employment.id)
            .order_by(WageHistory.effective_date.desc(), WageHistory.id.desc())
            .first()
        )
        latest_monthly = (
            monthly_equivalent(latest_wage.salary, latest_wage.salary_period) if latest_wage else None
        )
        if latest_monthly is None or abs(latest_monthly - report.monthly_income) >= 0.01:
            db.add(
                WageHistory(
                    wage_record_id=generate_wage_record_id(db),
                    employment_pk_id=employment.id,
                    trainee_pk_id=trainee.id,
                    salary=report.monthly_income,
                    salary_period="Monthly",
                    effective_date=today,
                    source="Trainee",
                    verification_status="Unverified",
                    notes=source_note,
                )
            )
    latest_status = (
        db.query(EmploymentStatusHistory)
        .filter(EmploymentStatusHistory.employment_pk_id == employment.id)
        .order_by(EmploymentStatusHistory.status_date.desc(), EmploymentStatusHistory.id.desc())
        .first()
    )
    current = latest_status.employment_status if latest_status else employment.employment_status
    if current != "Active":  # e.g. was On Leave / had left and rejoined
        db.add(
            EmploymentStatusHistory(
                status_record_id=generate_status_record_id(db),
                employment_pk_id=employment.id,
                trainee_pk_id=trainee.id,
                employment_status="Active",
                status_date=today,
                reason="Trainee self-report",
            )
        )


# ---------------------------------------------------------------------
# Employer confirmation
# ---------------------------------------------------------------------


def load_verification_context(db: Session, verification_id: str):
    verification = (
        db.query(EmployerVerification)
        .filter(EmployerVerification.verification_id == verification_id)
        .first()
    )
    if verification is None or verification.verification_method != "Employer Portal":
        raise _not_found()
    employment = db.query(EmploymentRecord).filter(EmploymentRecord.id == verification.employment_pk_id).one()
    trainee = db.query(Trainee).filter(Trainee.id == verification.trainee_pk_id).one()
    return verification, employment, trainee


def submit_employer_confirmation(
    db: Session, verification_id: str, answer: EmployerVerifySubmission
) -> str:
    verification, employment, trainee = load_verification_context(db, verification_id)
    verification = (  # lock + re-read, same reason as submit_self_report
        db.query(EmployerVerification)
        .filter(EmployerVerification.id == verification.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if verification.verification_status != "Pending":
        raise _conflict("This confirmation has already been submitted. Thank you!")

    today = date.today()
    verification.verification_status = "Verified" if answer.employment_confirmed else "Rejected"
    verification.verified_date = today
    verification.verified_by = answer.verified_by
    verification.verification_notes = answer.notes or "Submitted by the employer through the confirmation link."

    if answer.employment_confirmed:
        if answer.current_status:
            db.add(
                EmploymentStatusHistory(
                    status_record_id=generate_status_record_id(db),
                    employment_pk_id=employment.id,
                    trainee_pk_id=trainee.id,
                    employment_status=answer.current_status,
                    status_date=today,
                    reason="Employer confirmation",
                )
            )
        if answer.salary is not None:
            db.add(
                WageHistory(
                    wage_record_id=generate_wage_record_id(db),
                    employment_pk_id=employment.id,
                    trainee_pk_id=trainee.id,
                    salary=answer.salary,
                    salary_period=answer.salary_period or "Monthly",
                    effective_date=today,
                    source="Employer",
                    verification_status="Verified",
                    notes="Confirmed by the employer through the confirmation link",
                )
            )
    db.commit()
    return verification.verification_status


def create_verification_request(db: Session, employment: EmploymentRecord, employer_contact: str | None):
    verification = EmployerVerification(
        verification_id=generate_verification_id(db),
        employment_pk_id=employment.id,
        trainee_pk_id=employment.trainee_pk_id,
        employer_name=employment.company_name,
        employer_contact=employer_contact,
        verification_status="Pending",
        verification_method="Employer Portal",
        verification_notes="Confirmation link sent to the employer.",
    )
    db.add(verification)
    db.flush()
    return verification
