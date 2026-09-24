"""
Phase 6 tests — analytics & impact measurement.

These endpoints are read-only aggregations over whatever's already in
the database, so these tests mostly check response shape/types and that
nothing crashes (division by zero, empty tables, missing wage data),
rather than exact numbers — the exact numbers depend on everything
earlier tests have already inserted.
"""

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def test_overview_returns_expected_keys():
    response = client.get("/api/analytics/overview")
    assert response.status_code == 200
    body = response.json()
    expected_keys = {
        "total_trainees",
        "total_training_records",
        "completed_trainings",
        "ongoing_trainings",
        "dropped_trainings",
        "employed_trainees",
        "self_employed_trainees",
        "apprenticeship_trainees",
        "unemployed_trainees",
        "further_education_trainees",
        "not_reachable_trainees",
        "placement_rate",
        "employment_rate",
        "retention_rate",
    }
    assert expected_keys.issubset(body.keys())
    for key in expected_keys:
        assert isinstance(body[key], (int, float))


def test_overview_with_filters_does_not_crash():
    response = client.get(
        "/api/analytics/overview",
        params={"district": "Nonexistent District XYZ"},
    )
    assert response.status_code == 200
    body = response.json()
    # A district that matches no one should be all zeros, not an error.
    assert body["total_trainees"] == 0
    assert body["placement_rate"] == 0
    assert body["employment_rate"] == 0


def test_placement_rate_shape_and_no_division_by_zero():
    response = client.get("/api/analytics/placement-rate")
    assert response.status_code == 200
    body = response.json()
    assert "eligible_trainees" in body
    assert "placed_trainees" in body
    assert "placement_rate" in body
    assert 0 <= body["placement_rate"] <= 100


def test_employment_rate_shape():
    response = client.get("/api/analytics/employment-rate")
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["employment_rate"] <= 100


def test_retention_rate_shape():
    response = client.get("/api/analytics/retention-rate")
    assert response.status_code == 200
    body = response.json()
    assert "employed_trainees" in body
    assert "retained_trainees" in body
    assert 0 <= body["retention_rate"] <= 100


def test_wage_progression_shape():
    response = client.get("/api/analytics/wage-progression")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "employment_records",
        "average_initial_salary",
        "average_latest_salary",
        "average_salary_change",
        "average_salary_growth_percentage",
    ):
        assert key in body


def test_course_performance_is_a_list():
    response = client.get("/api/analytics/course-performance")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for row in body:
        assert 0 <= row["placement_rate"] <= 100


def test_provider_performance_is_a_list():
    response = client.get("/api/analytics/provider-performance")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_district_outcomes_is_a_list():
    response = client.get("/api/analytics/district-outcomes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_non_placement_reasons_percentages_are_sane():
    response = client.get("/api/analytics/non-placement-reasons")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for row in body:
        assert "reason" in row and "count" in row and "percentage" in row
        assert 0 <= row["percentage"] <= 100


def test_skill_gaps_shape():
    response = client.get("/api/analytics/skill-gaps")
    assert response.status_code == 200
    body = response.json()
    assert "followups_with_skill_gap" in body
    assert "additional_training_needed" in body
    assert 0 <= body["skill_gap_percentage"] <= 100


def test_all_previous_phase_routes_still_registered():
    """Sanity check: Phase 1-5 endpoints weren't accidentally dropped."""
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for expected in (
        "/api/trainees",
        "/api/outcomes",
        "/api/followups",
        "/api/followups/generate/{training_id}",
        "/api/employer-verifications",
        "/api/wage-history",
        "/api/analytics/overview",
    ):
        assert expected in paths, f"missing route: {expected}"


# --- Extended analytics (demographics, attrition, relevance, cohort, etc.) ---


def test_demographics_shape():
    response = client.get("/api/analytics/demographics")
    assert response.status_code == 200
    body = response.json()
    assert "gender_distribution" in body
    assert "age_groups" in body
    for row in body["gender_distribution"]:
        assert 0 <= row["placement_rate"] <= 100
    for row in body["age_groups"]:
        assert 0 <= row["placement_rate"] <= 100


def test_attrition_shape_and_no_invented_reasons():
    response = client.get("/api/analytics/attrition")
    assert response.status_code == 200
    body = response.json()
    assert "total_employment_records" in body
    assert "attrition_rate" in body
    assert "reasons" in body
    assert "note" in body  # explains data completeness, doesn't invent reasons
    assert 0 <= body["attrition_rate"] <= 100


def test_training_relevance_shape():
    response = client.get("/api/analytics/training-relevance")
    assert response.status_code == 200
    body = response.json()
    assert "total_responses" in body
    assert "ratings" in body
    assert set(body["ratings"].keys()) == {"1", "2", "3", "4", "5"}


def test_cohort_is_a_list():
    response = client.get("/api/analytics/cohort")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for row in body:
        assert 0 <= row["placement_rate"] <= 100


def test_accountability_has_definitions():
    response = client.get("/api/analytics/accountability")
    assert response.status_code == 200
    body = response.json()
    assert "definitions" in body
    assert isinstance(body["definitions"], dict)
    # No subjective labels anywhere in the response values
    banned_words = {"excellent", "poor", "best", "worst", "bad", "good"}
    flat_text = " ".join(str(v).lower() for v in body.values() if isinstance(v, str))
    assert not any(word in flat_text for word in banned_words)


def test_remedial_insights_is_a_list_of_data_backed_items():
    response = client.get("/api/analytics/remedial-insights")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for row in body:
        assert "area" in row and "metric" in row and "insight" in row


def test_resource_allocation_is_a_list():
    response = client.get("/api/analytics/resource-allocation")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for row in body:
        for key in (
            "district",
            "trainee_count",
            "unemployed_count",
            "skill_gap_count",
            "non_placement_count",
            "attrition_count",
            "additional_training_needed",
        ):
            assert key in row


def test_analytics_responses_never_expose_pii():
    """Part 21 — no phone/email/trainee_id in any analytics response."""
    endpoints = [
        "/api/analytics/overview",
        "/api/analytics/demographics",
        "/api/analytics/attrition",
        "/api/analytics/course-performance",
        "/api/analytics/district-outcomes",
        "/api/analytics/resource-allocation",
    ]
    for path in endpoints:
        body_text = client.get(path).text.lower()
        assert "phone" not in body_text
        assert "email" not in body_text
        assert "trn0" not in body_text  # a leaked TRN000001-style trainee_id
