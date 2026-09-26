"""
GET /api/trainees/{trainee_id}/wage-progression must return, for every job,
exactly what the three separate endpoints return.
"""

from tests.test_phase8_hardening import (
    add_status,
    add_wage,
    admin,
    analyst,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
)


def _separately(trainee_id: str) -> dict:
    history = get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"]
    return {
        "trainee_id": trainee_id,
        "employments": [
            {
                "employment": job,
                "summary": get_ok(admin, f"/api/employment/{job['employment_id']}/summary"),
                "wage_history": get_ok(admin, f"/api/employment/{job['employment_id']}/wage-history")["wage_history"],
            }
            for job in history
        ],
    }


def test_matches_the_separate_endpoints(isolated_db):
    trainee_id = make_trainee()
    first = make_employment(trainee_id, make_outcome(trainee_id, make_training(trainee_id), "Employed"),
                            company_name="Acme", joining_date="2024-01-10", salary=12000)
    second = make_employment(trainee_id, make_outcome(trainee_id, make_training(trainee_id), "Employed"),
                             company_name="Beta", joining_date="2025-02-01")
    add_wage(trainee_id, second, 180000, "Annual", "2025-02-01")
    add_wage(trainee_id, second, 17000, "Monthly", "2025-08-01")
    add_status(trainee_id, first, "Left Job", "2024-12-31", reason="Relocation")

    combined = get_ok(admin, f"/api/trainees/{trainee_id}/wage-progression")
    assert combined == _separately(trainee_id)
    jobs = combined["employments"]
    assert [j["employment"]["company_name"] for j in jobs] == ["Acme", "Beta"]
    assert jobs[0]["summary"]["current_status"] == "Left Job"
    assert jobs[0]["wage_history"] == [] and jobs[0]["summary"]["salary"]["initial"] == 12000.0
    assert jobs[1]["summary"]["salary"]["growth_percentage"] == 13.33  # 15,000 -> 17,000 a month


def test_no_jobs_and_access(isolated_db):
    trainee_id = make_trainee()
    assert get_ok(admin, f"/api/trainees/{trainee_id}/wage-progression") == {
        "trainee_id": trainee_id, "employments": [],
    }
    assert admin.get("/api/trainees/TRN999999/wage-progression").status_code == 404
    assert analyst.get(f"/api/trainees/{trainee_id}/wage-progression").status_code == 403
