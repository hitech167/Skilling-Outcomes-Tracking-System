"""
Analytics & Impact Measurement routes — Phase 6.

Every endpoint here is read-only: it queries the existing Phase 1-5
tables (trainees, training_records, outcomes + detail tables,
employer_verifications, wage_history, employment_status_history,
followups + followup_attempts/outcome_updates) and returns aggregated
statistics. Nothing here writes to the database, creates tables, or
adds sequences.

See services/analytics_service.py for the actual query/aggregation
logic and the definitions used (placement, retention, attrition, etc).

    GET /api/analytics/overview
    GET /api/analytics/placement-rate
    GET /api/analytics/employment-rate
    GET /api/analytics/retention-rate
    GET /api/analytics/wage-progression
    GET /api/analytics/course-performance
    GET /api/analytics/provider-performance
    GET /api/analytics/district-outcomes
    GET /api/analytics/demographics
    GET /api/analytics/non-placement-reasons
    GET /api/analytics/attrition
    GET /api/analytics/skill-gaps
    GET /api/analytics/training-relevance
    GET /api/analytics/cohort
    GET /api/analytics/accountability
    GET /api/analytics/remedial-insights
    GET /api/analytics/resource-allocation

No filters (district/provider/course/gender query params) are
implemented yet — see Part 19 of the spec, which allows deferring
filters if they would complicate the code; they can be added later by
filtering the row lists in analytics_service.py before aggregation.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.consent_scope import get_analytics_db
from schemas.analytics import (
    AccountabilityResponse,
    AttritionResponse,
    CohortItem,
    CoursePerformanceItem,
    DemographicsResponse,
    DistrictOutcomeItem,
    EmploymentRateResponse,
    NonPlacementReasonItem,
    OverviewResponse,
    PlacementRateResponse,
    ProviderPerformanceItem,
    RemedialInsightItem,
    ResourceAllocationItem,
    RetentionRateResponse,
    SkillGapResponse,
    TrainingRelevanceResponse,
    WageProgressionResponse,
)
from services import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics (Phase 6)"])


def _safe(db: Session, fn):
    """
    Run an analytics_service function. On a database error, log it and
    return 503 — never a raw 500, and never a zero-filled result that
    would look like a real "0% placement" figure on a dashboard.
    (Empty data is handled inside the service and returns real zeros /
    nulls / empty lists.)
    """
    try:
        return fn(db)
    except SQLAlchemyError:
        logger.exception("Database error while computing analytics (%s)", fn.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics are unavailable right now. Please try again.",
        )


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Overall dashboard counts and rates",
)
def overview(
    district: str | None = Query(None),
    db: Session = Depends(get_analytics_db),
):
    return _safe(
        db,
        lambda s: analytics_service.get_overview(s, district=district),
    )


@router.get(
    "/placement-rate",
    response_model=PlacementRateResponse,
    summary="Placement rate (Employed + Self-employed + Apprenticeship) among completed trainings",
)
def placement_rate(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_placement_rate)


@router.get(
    "/employment-rate",
    response_model=EmploymentRateResponse,
    summary="Employment rate among completed trainings",
)
def employment_rate(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_employment_rate)


@router.get(
    "/retention-rate",
    response_model=RetentionRateResponse,
    summary="Job retention rate — latest known employment status = Active",
)
def retention_rate(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_retention_rate)


@router.get(
    "/wage-progression",
    response_model=WageProgressionResponse,
    summary="Average salary change from first to latest recorded wage",
)
def wage_progression(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_wage_progression)


@router.get(
    "/course-performance",
    response_model=list[CoursePerformanceItem],
    summary="Outcome statistics grouped by course_name",
)
def course_performance(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_course_performance)


@router.get(
    "/provider-performance",
    response_model=list[ProviderPerformanceItem],
    summary="Outcome statistics grouped by provider_name",
)
def provider_performance(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_provider_performance)


@router.get(
    "/district-outcomes",
    response_model=list[DistrictOutcomeItem],
    summary="Outcome statistics grouped by trainee district",
)
def district_outcomes(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_district_outcomes)


@router.get(
    "/demographics",
    response_model=DemographicsResponse,
    summary="Gender distribution and age-group outcome statistics",
)
def demographics(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_demographics)


@router.get(
    "/non-placement-reasons",
    response_model=list[NonPlacementReasonItem],
    summary="Non-placement records grouped by reason_category",
)
def non_placement_reasons(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_non_placement_reasons)


@router.get(
    "/attrition",
    response_model=AttritionResponse,
    summary="Attrition rate and reasons among employment records",
)
def attrition(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_attrition)


@router.get(
    "/skill-gaps",
    response_model=SkillGapResponse,
    summary="Skill-gap and additional-training-needed rates from follow-up outcome updates",
)
def skill_gaps(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_skill_gaps)


@router.get(
    "/training-relevance",
    response_model=TrainingRelevanceResponse,
    summary="Distribution and average of training_relevance (1-5) ratings",
)
def training_relevance(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_training_relevance)


@router.get(
    "/cohort",
    response_model=list[CohortItem],
    summary="Outcome statistics grouped by training-completion month (cohort)",
)
def cohort(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_cohort_analytics)


@router.get(
    "/accountability",
    response_model=AccountabilityResponse,
    summary="Programme-level measured indicators (no subjective labels)",
)
def accountability(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_accountability)


@router.get(
    "/remedial-insights",
    response_model=list[RemedialInsightItem],
    summary="Rule-based, data-backed observations (no AI/ML, no rankings)",
)
def remedial_insights(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_remedial_insights)


@router.get(
    "/resource-allocation",
    response_model=list[ResourceAllocationItem],
    summary="District-wise measurable indicators for resource-allocation decisions",
)
def resource_allocation(db: Session = Depends(get_analytics_db)):
    return _safe(db, analytics_service.get_resource_allocation)
