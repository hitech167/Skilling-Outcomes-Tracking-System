"""
GET /api/insights/all must return exactly what the ten per-section
endpoints return, so the Insights page can make one request instead of ten.
"""

from tests.test_phase8_hardening import (
    add_status,
    add_wage,
    admin,
    analyst,
    anon,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
)

SECTIONS = {
    "summary": "/api/insights/summary",
    "remedial_actions": "/api/insights/remedial-actions",
    "accountability": "/api/insights/accountability",
    "skill_gaps_by_course": "/api/insights/skill-gaps/by-course",
    "resource_allocation": "/api/insights/resource-allocation",
    "non_placement": "/api/insights/non-placement",
    "attrition": "/api/insights/attrition",
    "training_relevance": "/api/insights/training-relevance",
    "longitudinal_outcomes": "/api/insights/longitudinal-outcomes",
    "data_quality": "/api/insights/data-quality",
}


def test_all_matches_the_individual_endpoints(isolated_db):
    for i in range(3):
        trainee_id = make_trainee(full_name=f"Trainee {i}")
        outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
        employment_id = make_employment(trainee_id, outcome_id)
        add_wage(trainee_id, employment_id, 15000 + i * 1000, "Monthly", "2025-05-15")
        if i == 0:
            add_status(trainee_id, employment_id, "Left Job", "2025-09-01", reason="Relocation")
    unemployed = make_trainee()
    make_outcome(unemployed, make_training(unemployed), "Unemployed")

    combined = get_ok(analyst, "/api/insights/all")
    assert set(combined) == set(SECTIONS)
    for key, path in SECTIONS.items():
        assert combined[key] == get_ok(analyst, path), key
    # Longitudinal keeps its digit-first field names inside the combined body too
    assert "30_day_followups_completed" in combined["longitudinal_outcomes"]


def test_all_access(isolated_db):
    assert admin.get("/api/insights/all").status_code == 200
    assert anon.get("/api/insights/all").status_code == 401
