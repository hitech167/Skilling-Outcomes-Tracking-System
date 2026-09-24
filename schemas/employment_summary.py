"""
Pydantic schemas for Phase 4 — read-only combined views.

These endpoints don't write anything; they assemble data already stored
in employment_records, employer_verifications, wage_history and
employment_status_history into one response.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class VerificationSummary(BaseModel):
    status: str
    method: str


class SalarySummary(BaseModel):
    """
    initial/latest are the amounts exactly as recorded; their periods are
    given separately. The *_monthly fields normalise both to a monthly
    figure (Annual / 12) so they can be compared.
    """

    initial: Optional[float] = None
    latest: Optional[float] = None
    period: Optional[str] = None  # period of `latest` (kept for compatibility)
    initial_period: Optional[str] = None
    initial_monthly: Optional[float] = None
    latest_monthly: Optional[float] = None
    growth_percentage: Optional[float] = None


class EmploymentSummaryResponse(BaseModel):
    """Body of GET /api/employment/{employment_id}/summary"""

    employment_id: str
    company_name: str
    job_role: str
    joining_date: date

    verification: Optional[VerificationSummary] = None
    salary: SalarySummary
    current_status: str

    wage_history_count: int
    status_history_count: int


class EmploymentHistoryItem(BaseModel):
    employment_id: str
    company_name: str
    job_role: str
    joining_date: date
    current_status: str


class TraineeEmploymentHistoryResponse(BaseModel):
    """Body of GET /api/trainees/{trainee_id}/employment-history"""

    trainee_id: str
    employment_history: list[EmploymentHistoryItem]
