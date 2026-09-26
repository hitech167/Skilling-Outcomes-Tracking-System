"""
Consent changes with an audit trail.

Every grant / withdrawal (at registration, by staff, or by the trainee
from their own link) is written to trainee_consent_history with who
recorded it and how, so consent can be evidenced. trainees.consent_given
stays the single flag the rest of the app checks.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Trainee, TraineeConsentHistory


def set_consent(
    db: Session,
    trainee: Trainee,
    given: bool,
    source: str,
    method: Optional[str] = None,
    recorded_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Set the flag and log it. `source` is registration | admin | self. Caller commits."""
    trainee.consent_given = given
    trainee.consent_date = datetime.now(timezone.utc)
    db.add(
        TraineeConsentHistory(
            trainee_pk_id=trainee.id,
            consent_given=given,
            source=source,
            method=method,
            recorded_by=recorded_by,
            notes=notes,
        )
    )
