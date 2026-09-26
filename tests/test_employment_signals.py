"""External employment-signal CSV import."""

from tests.test_phase8_hardening import admin, analyst, anon, get_ok, make_trainee, make_training


def _upload(csv_text, source="EPFO", dry_run=False, client=admin):
    return client.post(
        "/api/employment-signals/import",
        files={"file": ("signals.csv", csv_text.encode(), "text/csv")},
        data={"source": source, "dry_run": str(dry_run).lower()},
    )


def test_import_creates_verified_employment_and_is_idempotent(isolated_db):
    trainee_id = make_trainee()
    make_training(trainee_id)
    csv_text = (
        "trainee_id,employer_name,job_role,start_date,monthly_salary,reference\n"
        f"{trainee_id},Volt Works Pvt Ltd,Electrician,2025-06-01,17000,UAN123\n"
    )

    dry = _upload(csv_text, dry_run=True).json()
    assert dry["created"] == 1 and dry["dry_run"] is True
    assert get_ok(admin, f"/api/trainees/{trainee_id}/outcomes")["outcomes"] == []  # dry run saved nothing

    result = _upload(csv_text).json()
    assert result["created"] == 1

    outcomes = get_ok(admin, f"/api/trainees/{trainee_id}/outcomes")
    assert [o["outcome_type"] for o in outcomes["outcomes"]] == ["Employed"]
    employment_id = get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"][0]["employment_id"]
    verification = get_ok(admin, f"/api/employment/{employment_id}/verification")
    assert verification["verification_status"] == "Verified" and verification["verified_by"] == "EPFO"

    # second upload does not duplicate
    again = _upload(csv_text).json()
    assert again["created"] == 0 and again["already_recorded"] == 1


def test_import_reports_bad_rows_without_failing_file(isolated_db):
    ok = make_trainee()
    make_training(ok)
    no_training = make_trainee()
    withdrawn = make_trainee()
    make_training(withdrawn)
    admin.post(f"/api/trainees/{withdrawn}/consent", json={"consent_given": False})
    csv_text = (
        "trainee_id,employer_name,start_date,monthly_salary\n"
        f"{ok},Acme,2025-06-01,\n"
        "TRN999999,Acme,2025-06-01,\n"
        f"{no_training},Acme,2025-06-01,\n"
        f"{withdrawn},Acme,2025-06-01,\n"
        f"{ok},Beta,not-a-date,\n"
        f"{ok},Gamma,2999-01-01,\n"
    )
    r = _upload(csv_text).json()
    assert (r["created"], r["trainee_not_found"], r["no_training"], r["no_consent"], r["invalid"]) == (1, 1, 1, 1, 2)
    assert {p["row"] for p in r["problems"]} == {3, 4, 6, 7}


def test_import_matches_by_phone_and_validates_file_and_access(isolated_db):
    trainee_id = make_trainee()
    make_training(trainee_id)
    phone = get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"]
    r = _upload(f"phone,employer_name,start_date\n+91 {phone},Acme,2025-06-01\n").json()
    assert r["created"] == 1

    assert _upload("foo,bar\n1,2\n").status_code == 422
    assert _upload("trainee_id,employer_name,start_date\n", source="").status_code == 422
    assert _upload("trainee_id,employer_name,start_date\n", client=analyst).status_code == 403
    assert _upload("trainee_id,employer_name,start_date\n", client=anon).status_code == 401
