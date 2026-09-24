"""
Basic Phase 7 tests — insights endpoints.

Like the other test files in this suite, these hit the real database
configured in .env, so run them against a test/empty Supabase project,
not production data. They only check status codes and response shapes
(not exact numbers), since the numbers depend on whatever data already
exists in the database.

Run with:  pytest -v
"""

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def test_skill_gaps_overview():
    response = client.get("/api/insights/skill-gaps")
    assert response.status_code == 200
    body = response.json()
    assert "skill_gap_percentage" in body
    assert "average_training_relevance" in body


def test_skill_gaps_by_course_is_a_list():
    response = client.get("/api/insights/skill-gaps/by-course")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_non_placement_analysis_handles_empty_data():
    response = client.get("/api/insights/non-placement")
    assert response.status_code == 200
    body = response.json()
    assert body["total_records"] >= 0
    if body["total_records"] == 0:
        assert body["reasons"] == []
        assert body["most_frequent_reason"] is None


def test_attrition_analysis_no_division_by_zero():
    response = client.get("/api/insights/attrition")
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["attrition_rate"] <= 100.0


def test_training_relevance_buckets_sum_to_total():
    response = client.get("/api/insights/training-relevance")
    assert response.status_code == 200
    body = response.json()
    bucket_sum = (
        body["low_relevance_count"]
        + body["medium_relevance_count"]
        + body["high_relevance_count"]
    )
    assert bucket_sum == body["total_responses"]


def test_additional_training_overview():
    response = client.get("/api/insights/additional-training")
    assert response.status_code == 200
    assert "additional_training_percentage" in response.json()


def test_additional_training_by_course_is_a_list():
    response = client.get("/api/insights/additional-training/by-course")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_longitudinal_outcomes_uses_spec_key_names():
    response = client.get("/api/insights/longitudinal-outcomes")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "training_completed",
        "30_day_followups_completed",
        "90_day_followups_completed",
        "6_month_followups_completed",
        "12_month_followups_completed",
        "employed_trainees",
        "retained_trainees",
    ):
        assert key in body


def test_programme_improvement_shape():
    response = client.get("/api/insights/programme-improvement")
    assert response.status_code == 200
    body = response.json()
    assert "metrics" in body
    assert "observations" in body
    assert isinstance(body["observations"], list)


def test_remedial_actions_is_a_list():
    response = client.get("/api/insights/remedial-actions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_resource_allocation_is_a_list():
    response = client.get("/api/insights/resource-allocation")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_accountability_has_courses_and_providers():
    response = client.get("/api/insights/accountability")
    assert response.status_code == 200
    body = response.json()
    assert "courses" in body
    assert "providers" in body


def test_data_quality_shape():
    response = client.get("/api/insights/data-quality")
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["followup_completion_rate"] <= 100.0


def test_summary_shape():
    response = client.get("/api/insights/summary")
    assert response.status_code == 200
    body = response.json()
    assert "metrics" in body
    assert "insights" in body


def test_previous_phases_still_registered():
    # Regression check — a couple of Phase 1/3/6 routes should still work.
    assert client.get("/api/trainees/DOES_NOT_EXIST").status_code == 404
    assert client.get("/api/analytics/overview").status_code == 200
