"""
Skill Gaps, Attrition & Improvement Intelligence routes — Phase 7.

Builds on top of routes/analytics.py (Phase 6) rather than duplicating
it: every endpoint here calls services/insights_service.py, which in
turn reuses services/analytics_service.py's functions wherever the
underlying number is the same (overall placement/employment/retention/
non-placement/attrition/skill-gap/training-relevance figures) and only
adds new logic for by-course/by-provider breakdowns, longitudinal
follow-up-stage counts, worded observations, structured remedial
actions, and data-quality checks.

Everything is read-only — no writes, no new tables/sequences.

    GET /api/insights/skill-gaps
    GET /api/insights/skill-gaps/by-course
    GET /api/insights/non-placement
    GET /api/insights/attrition
    GET /api/insights/training-relevance
    GET /api/insights/additional-training
    GET /api/insights/additional-training/by-course
    GET /api/insights/longitudinal-outcomes
    GET /api/insights/programme-improvement
    GET /api/insights/remedial-actions
    GET /api/insights/resource-allocation
    GET /api/insights/accountability
    GET /api/insights/data-quality
    GET /api/insights/summary
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.consent_scope import get_analytics_db
from schemas.insights import (
    AccountabilityResponse,
    AdditionalTrainingOverviewResponse,
    AttritionAnalysisResponse,
    CourseFollowupStatsItem,
    DataQualityResponse,
    InsightSummaryResponse,
    LongitudinalOutcomesResponse,
    NonPlacementAnalysisResponse,
    ProgrammeImprovementResponse,
    RemedialActionItem,
    ResourceAllocationItem,
    SkillGapOverviewResponse,
    TrainingRelevanceInsightsResponse,
)
from services import insights_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/insights", tags=["Insights (Phase 7)"])


def _safe(db: Session, fn):
    """Same pattern as routes/analytics.py — a DB error becomes 503, never fabricated zeros."""
    try:
        return fn(db)
    except SQLAlchemyError:
        logger.exception("Database error while computing insights (%s)", fn.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Insights are unavailable right now. Please try again.",
        )


@router.get(
    "/skill-gaps",
    response_model=SkillGapOverviewResponse,
    summary="Overall skill-gap and additional-training-need statistics from follow-up data",
)
def skill_gaps(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_skill_gaps_overview)


@router.get(
    "/skill-gaps/by-course",
    response_model=list[CourseFollowupStatsItem],
    summary="Skill-gap statistics grouped by course_name",
)
def skill_gaps_by_course(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_skill_gaps_by_course)


@router.get(
    "/non-placement",
    response_model=NonPlacementAnalysisResponse,
    summary="Non-placement records grouped by reason, plus the most frequent reason",
)
def non_placement(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_non_placement_analysis)


@router.get(
    "/attrition",
    response_model=AttritionAnalysisResponse,
    summary="Attrition rate and reasons (flags when structured reason data is unavailable)",
)
def attrition(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_attrition_analysis)


@router.get(
    "/training-relevance",
    response_model=TrainingRelevanceInsightsResponse,
    summary="Training relevance responses bucketed into Low (1-2) / Medium (3) / High (4-5)",
)
def training_relevance(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_training_relevance_insights)


@router.get(
    "/additional-training",
    response_model=AdditionalTrainingOverviewResponse,
    summary="Overall additional-training-needed statistics",
)
def additional_training(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_additional_training_overview)


@router.get(
    "/additional-training/by-course",
    response_model=list[CourseFollowupStatsItem],
    summary="Additional-training-needed statistics grouped by course_name",
)
def additional_training_by_course(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_additional_training_by_course)


@router.get(
    "/longitudinal-outcomes",
    response_model=LongitudinalOutcomesResponse,
    summary="Training-completion through follow-up-stage and employment/retention counts",
)
def longitudinal_outcomes(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_longitudinal_outcomes)


@router.get(
    "/programme-improvement",
    response_model=ProgrammeImprovementResponse,
    summary="Key metrics plus worded, rule-based programme-improvement observations",
)
def programme_improvement(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_programme_improvement)


@router.get(
    "/remedial-actions",
    response_model=list[RemedialActionItem],
    summary="Structured, rule-based remedial-action suggestions with the triggering metric",
)
def remedial_actions(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_remedial_actions)


@router.get(
    "/resource-allocation",
    response_model=list[ResourceAllocationItem],
    summary="District-wise measurable indicators for resource-allocation decisions",
)
def resource_allocation(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_resource_allocation)


@router.get(
    "/accountability",
    response_model=AccountabilityResponse,
    summary="Factual, unranked course/provider accountability indicators",
)
def accountability(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_accountability)


@router.get(
    "/data-quality",
    response_model=DataQualityResponse,
    summary="Aggregated counts of missing values across trainee/training/employment/follow-up records",
)
def data_quality(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_data_quality)


@router.get(
    "/summary",
    response_model=InsightSummaryResponse,
    summary="Combined key metrics and rule-based insights",
)
def summary(db: Session = Depends(get_analytics_db)):
    return _safe(db, insights_service.get_insight_summary)
