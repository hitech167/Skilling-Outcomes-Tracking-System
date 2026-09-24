"""
Pydantic response schemas for Phase 6 — Analytics & Impact Measurement.

Read-only response shapes only; there are no request/create schemas in
this module because every analytics endpoint is a GET computed from
existing Phase 1-5 data.
"""

from typing import Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    total_trainees: int
    total_training_records: int
    enrolled_trainings: int
    ongoing_trainings: int
    completed_trainings: int
    dropped_trainings: int
    employed_trainees: int
    self_employed_trainees: int
    apprenticeship_trainees: int
    unemployed_trainees: int
    further_education_trainees: int
    not_reachable_trainees: int
    placed_trainees: int
    placement_rate: float
    employment_rate: float
    retention_rate: float


class PlacementRateResponse(BaseModel):
    eligible_trainees: int
    placed_trainees: int
    placement_rate: float


class EmploymentRateResponse(BaseModel):
    eligible_trainees: int
    employed_trainees: int
    employment_rate: float


class RetentionRateResponse(BaseModel):
    employed_trainees: int
    retained_trainees: int
    retention_rate: float
    definition: str


class WageProgressionResponse(BaseModel):
    employment_records: int
    employment_records_with_wage_data: int
    employment_records_with_wage_progression: int = 0
    salary_basis: str = "Monthly (Annual salaries divided by 12)"
    average_initial_salary: Optional[float] = None
    average_latest_salary: Optional[float] = None
    average_salary_change: Optional[float] = None
    average_salary_growth_percentage: Optional[float] = None


class GroupPerformanceItem(BaseModel):
    total_trainees: int
    completed: int
    placed: int
    employed: int
    self_employed: int
    apprenticeship: int
    unemployed: int
    placement_rate: float


class CoursePerformanceItem(GroupPerformanceItem):
    course_name: str


class ProviderPerformanceItem(GroupPerformanceItem):
    provider_name: str


class DistrictOutcomeItem(GroupPerformanceItem):
    district: str


class GenderDistributionItem(BaseModel):
    gender: str
    total_trainees: int
    completed_trainees: int = 0
    employed: int
    self_employed: int
    apprenticeship: int
    unemployed: int
    placement_rate: float


class AgeGroupItem(BaseModel):
    age_group: str
    total_trainees: int
    completed_trainees: int = 0
    employed: int
    placed: int
    unemployed: int
    placement_rate: float


class DemographicsResponse(BaseModel):
    gender_distribution: list[GenderDistributionItem]
    age_groups: list[AgeGroupItem]


class NonPlacementReasonItem(BaseModel):
    reason: str
    count: int
    percentage: float


class AttritionReasonItem(BaseModel):
    reason: str
    count: int


class AttritionResponse(BaseModel):
    total_employment_records: int
    attrition_records: int
    attrition_rate: float
    reasons: list[AttritionReasonItem]
    reason_data_complete: bool
    note: Optional[str] = None


class SkillGapResponse(BaseModel):
    followups_with_skill_gap: int
    additional_training_needed: int
    skill_gap_percentage: float


class TrainingRelevanceResponse(BaseModel):
    total_responses: int
    average_relevance: Optional[float] = None
    ratings: dict[str, int]


class CohortItem(BaseModel):
    cohort: str
    total_trainees: int
    completed: int
    placed: int
    employed: int
    self_employed: int
    apprenticeship: int
    unemployed: int
    placement_rate: float


class AccountabilityResponse(BaseModel):
    total_trainees: int
    completion_rate: float
    placement_rate: float
    employment_rate: float
    retention_rate: float
    average_training_relevance: Optional[float] = None
    skill_gap_percentage: float
    non_placement_count: int
    attrition_rate: float
    average_salary_growth_percentage: Optional[float] = None
    definitions: Optional[dict[str, str]] = None


class RemedialInsightItem(BaseModel):
    area: str
    metric: float
    insight: str


class ResourceAllocationItem(BaseModel):
    district: str
    trainee_count: int
    unemployed_count: int
    skill_gap_count: int
    non_placement_count: int
    attrition_count: int
    additional_training_needed: int
