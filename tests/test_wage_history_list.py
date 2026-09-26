"""
Tests for GET /api/wage-history (wage records across trainees).

Each test gets its own empty in-memory database (the isolated_db fixture in conftest.py).
"""

from tests.test_phase8_hardening import (
    add_wage,
    admin,
    analyst,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
)


def _employment(full_name: str, company: str = "Volt Works Pvt Ltd") -> tuple[str, str]:
    trainee_id = make_trainee(full_name=full_name)
    outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
    return trainee_id, make_employment(trainee_id, outcome_id, company_name=company)


def _trainee_report(trainee_id, employment_id, salary, effective_date):
    res = admin.post(
        "/api/wage-history",
        json={"employment_id": employment_id, "trainee_id": trainee_id, "salary": salary,
              "salary_period": "Monthly", "effective_date": effective_date, "source": "Trainee"},
    )
    assert res.status_code == 201, res.text


def test_list_joins_trainee_and_employer_newest_first(isolated_db):
    a, emp_a = _employment("Asha Patil", "Acme Ltd")
    b, emp_b = _employment("Bilal Khan", "Beta Corp")
    add_wage(a, emp_a, 15000, "Monthly", "2025-01-01")
    add_wage(b, emp_b, 240000, "Annual", "2025-03-01")
    _trainee_report(a, emp_a, 17000, "2025-06-01")

    rows = get_ok(admin, "/api/wage-history")
    assert [(r["trainee_name"], r["salary"], r["effective_date"]) for r in rows] == [
        ("Asha Patil", 17000.0, "2025-06-01"),
        ("Bilal Khan", 240000.0, "2025-03-01"),
        ("Asha Patil", 15000.0, "2025-01-01"),
    ]
    assert rows[1]["company_name"] == "Beta Corp" and rows[1]["salary_period"] == "Annual"
    assert rows[1]["job_role"] and rows[1]["employment_id"] == emp_b


def test_list_filters(isolated_db):
    a, emp_a = _employment("Asha Patil")
    b, emp_b = _employment("Bilal Khan")
    add_wage(a, emp_a, 15000, "Monthly", "2025-01-01")  # source Employer
    _trainee_report(a, emp_a, 17000, "2025-06-01")
    add_wage(b, emp_b, 20000, "Monthly", "2025-02-01")

    by_source = get_ok(admin, "/api/wage-history", params={"source": "trainee"})
    assert [r["salary"] for r in by_source] == [17000.0]
    by_status = get_ok(admin, "/api/wage-history", params={"verification_status": "Unverified"})
    assert len(by_status) == 3  # add_wage uses the default verification status
    by_trainee = get_ok(admin, "/api/wage-history", params={"trainee_id": b.lower()})
    assert [r["trainee_id"] for r in by_trainee] == [b]

    assert admin.get("/api/wage-history", params={"source": "Rumour"}).status_code == 422
    assert admin.get("/api/wage-history", params={"verification_status": "Maybe"}).status_code == 422


def test_list_is_admin_only(isolated_db):
    assert analyst.get("/api/wage-history").status_code == 403
