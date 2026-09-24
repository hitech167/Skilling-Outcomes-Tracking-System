"""
Pydantic response schemas for Phase 7 — Skill Gaps, Attrition & Improvement
Intelligence. Read-only, GET-only, same as Phase 6's schemas/analytics.py.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SkillGapOverviewResponse(BaseModel):
    total_followups: int
    followups_with_skill_gap: int
    skill_gap_percentage: float
    additional_training_needed: int
    additional_training_percentage: float
    average_training_relevance: Optional[float] = None


class CourseFollowupStatsItem(BaseModel):
    course_name: str
    total_followups: int
    skill_gap_count: int
    skill_gap_percentage: float
    additional_training_count: int
    additional_training_percentage: float
    average_training_relevance: Optional[float] = None


class NonPlacementReasonItem(BaseModel):
    reason: str
    count: int
    percentage: float


class NonPlacementAnalysisResponse(BaseModel):
    total_records: int
    reasons: list[NonPlacementReasonItem]
    most_frequent_reason: Optional[str] = None


class AttritionReasonItem(BaseModel):
    reason: str
    count: int
    percentage: float


class AttritionAnalysisResponse(BaseModel):
    total_employment_records: int
    attrition_records: int
    attrition_rate: float
    reasons: list[AttritionReasonItem]
    reason_data_available: bool


class TrainingRelevanceInsightsResponse(BaseModel):
    total_responses: int
    average_rating: Optional[float] = None
    low_relevance_count: int
    medium_relevance_count: int
    high_relevance_count: int


class AdditionalTrainingOverviewResponse(BaseModel):
    total_responses: int
    additional_training_needed_count: int
    additional_training_percentage: float


class LongitudinalOutcomesResponse(BaseModel):
    """
    Field names starting with a digit ("30_day_...") aren't valid Python
    identifiers, so each is given a Python-safe name with a matching
    alias — FastAPI serializes response models by alias by default, so
    the JSON output still has the exact keys the spec asks for.
    """

    training_completed: int
    day_30_followups_completed: int = Field(..., alias="30_day_followups_completed")
    day_90_followups_completed: int = Field(..., alias="90_day_followups_completed")
    month_6_followups_completed: int = Field(..., alias="6_month_followups_completed")
    month_12_followups_completed: int = Field(..., alias="12_month_followups_completed")
    employed_trainees: int
    retained_trainees: int

    model_config = {"populate_by_name": True}


class ProgrammeObservationItem(BaseModel):
    area: str
    observation: str


class ProgrammeMetrics(BaseModel):
    placement_rate: float
    employment_rate: float
    retention_rate: float
    skill_gap_percentage: float
    additional_training_percentage: float
    average_training_relevance: Optional[float] = None
    attrition_rate: float
    average_salary_growth_percentage: Optional[float] = None


class ProgrammeImprovementResponse(BaseModel):
    metrics: ProgrammeMetrics
    non_placement_reasons: list[NonPlacementReasonItem]
    observations: list[ProgrammeObservationItem]


class RemedialActionItem(BaseModel):
    area: str
    metric: dict[str, float]
    action: str


class ResourceAllocationItem(BaseModel):
    district: str
    trainee_count: int
    completed_count: int
    unemployed_count: int
    skill_gap_count: int
    additional_training_count: int
    non_placement_count: int
    attrition_count: int


class AccountabilityItem(BaseModel):
    name: str
    total_trainees: int
    completion_rate: float
    placement_rate: float
    employment_rate: float
    retention_rate: float
    average_training_relevance: Optional[float] = None
    skill_gap_percentage: float
    attrition_rate: float
    average_salary_growth_percentage: Optional[float] = None


class AccountabilityResponse(BaseModel):
    courses: list[AccountabilityItem]
    providers: list[AccountabilityItem]


class DataQualityResponse(BaseModel):
    trainees_missing_phone: int
    trainees_missing_location: int
    trainees_missing_gender: int
    trainees_missing_dob: int
    training_missing_completion_date: int
    training_missing_attendance: int
    training_missing_assessment: int
    employment_missing_salary: int
    employment_missing_joining_date: int
    completed_training_without_outcome: int = 0
    employment_without_wage_history: int = 0
    employment_without_verification: int = 0
    employment_without_status_history: int = 0
    trainees_consent_withdrawn_excluded: int = 0
    possible_duplicate_trainees: int = 0
    followups_not_completed: int
    followups_not_reachable: int
    followup_completion_rate: float


class SummaryMetrics(BaseModel):
    placement_rate: float
    employment_rate: float
    retention_rate: float
    average_salary_growth_percentage: Optional[float] = None
    skill_gap_percentage: float
    additional_training_percentage: float
    average_training_relevance: Optional[float] = None
    attrition_rate: float
    top_non_placement_reason: Optional[str] = None
    followup_completion_rate: float


class InsightSummaryResponse(BaseModel):
    metrics: SummaryMetrics
    insights: list[ProgrammeObservationItem]
