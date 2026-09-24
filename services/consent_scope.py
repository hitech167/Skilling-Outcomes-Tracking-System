"""
Consent scope for analytics / insights.

A trainee who has withdrawn consent must drop out of the statistics, not
just stop being contacted. Rather than editing every query in
analytics_service / insights_service, analytics sessions carry a flag
and this ORM hook adds the filter to every SELECT they run:

    trainees                    -> consent_given IS TRUE
    any table with trainee_pk_id -> trainee_pk_id IN (consented trainees)

Record-level (admin) endpoints use normal sessions and still see
everything, so nothing is hidden from the people managing the records
and nothing is deleted.
"""

from fastapi import Depends
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria

from database.connection import get_db
from database.models import (
    ApprenticeshipRecord,
    EmployerVerification,
    EmploymentRecord,
    EmploymentStatusHistory,
    FollowUp,
    FollowUpOutcomeUpdate,
    NonPlacementRecord,
    Outcome,
    SelfEmploymentRecord,
    Trainee,
    TrainingRecord,
    WageHistory,
)

CONSENT_SCOPE_KEY = "consented_only"
SKIP_SCOPE_OPTION = "skip_consent_scope"

_TRAINEE_LINKED_MODELS = (
    TrainingRecord,
    Outcome,
    EmploymentRecord,
    SelfEmploymentRecord,
    ApprenticeshipRecord,
    NonPlacementRecord,
    FollowUp,
    FollowUpOutcomeUpdate,
    EmployerVerification,
    WageHistory,
    EmploymentStatusHistory,
)


@event.listens_for(Session, "do_orm_execute")
def _apply_consent_scope(state):
    if (
        not state.is_select
        or not state.session.info.get(CONSENT_SCOPE_KEY)
        or state.execution_options.get(SKIP_SCOPE_OPTION)
        or state.is_column_load
        or state.is_relationship_load
    ):
        return
    consented_ids = select(Trainee.id).where(Trainee.consent_given.is_(True))
    options = [with_loader_criteria(Trainee, Trainee.consent_given.is_(True), include_aliases=True)]
    options += [
        with_loader_criteria(model, model.trainee_pk_id.in_(consented_ids), include_aliases=True)
        for model in _TRAINEE_LINKED_MODELS
    ]
    state.statement = state.statement.options(*options)


def get_analytics_db(db: Session = Depends(get_db)) -> Session:
    """get_db, but every query only sees trainees with active consent."""
    db.info[CONSENT_SCOPE_KEY] = True
    return db
