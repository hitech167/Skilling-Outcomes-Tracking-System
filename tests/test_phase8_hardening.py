"""
Phase 8 — final SIH26135 compliance / hardening tests.

Every test here runs against its OWN fresh, in-memory SQLite database
(see tests/conftest.py). That makes it possible to assert exact
analytics values, and to test a genuinely empty database, without
touching development data.

PostgreSQL sequences are emulated with a `nextval()` SQL function
registered on the SQLite connection; everything else is the real app:
same routes, services, schemas and auth.

Covers:
  * access control (JWT, admin vs analyst, public endpoints)
  * consent behaviour, stable identity + contact updates
  * full end-to-end journey with ID/relationship checks at each stage
  * all six outcome types and the placement definition
  * longitudinal wage (mixed Monthly/Annual) + status history + attrition
  * follow-up generation idempotence
  * empty database and partial-data stability
  * privacy of aggregate endpoints
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.auth_helpers import ADMIN_HEADERS, ANALYST_HEADERS, TEST_USERS
from database import models
from database.connection import get_db
from main import app
from services.analytics_service import wage_progression_for

admin = TestClient(app, headers=ADMIN_HEADERS)
analyst = TestClient(app, headers=ANALYST_HEADERS)
anon = TestClient(app)

ANALYTICS_ENDPOINTS = [
    "/api/analytics/overview",
    "/api/analytics/placement-rate",
    "/api/analytics/employment-rate",
    "/api/analytics/retention-rate",
    "/api/analytics/wage-progression",
    "/api/analytics/course-performance",
    "/api/analytics/provider-performance",
    "/api/analytics/district-outcomes",
    "/api/analytics/demographics",
    "/api/analytics/non-placement-reasons",
    "/api/analytics/attrition",
    "/api/analytics/skill-gaps",
    "/api/analytics/training-relevance",
    "/api/analytics/cohort",
    "/api/analytics/accountability",
    "/api/analytics/remedial-insights",
    "/api/analytics/resource-allocation",
]
INSIGHT_ENDPOINTS = [
    "/api/insights/skill-gaps",
    "/api/insights/skill-gaps/by-course",
    "/api/insights/non-placement",
    "/api/insights/attrition",
    "/api/insights/training-relevance",
    "/api/insights/additional-training",
    "/api/insights/additional-training/by-course",
    "/api/insights/longitudinal-outcomes",
    "/api/insights/programme-improvement",
    "/api/insights/remedial-actions",
    "/api/insights/resource-allocation",
    "/api/insights/accountability",
    "/api/insights/data-quality",
    "/api/insights/summary",
]
AGGREGATE_ENDPOINTS = ANALYTICS_ENDPOINTS + INSIGHT_ENDPOINTS


# ---------------------------------------------------------------------
# Small builders (each asserts success and returns the public ID)
# ---------------------------------------------------------------------

_phone_numbers = itertools.count(1)


def new_phone() -> str:
    return f"98{next(_phone_numbers):08d}"


def make_trainee(**overrides) -> str:
    payload = {
        "full_name": "Test Trainee",
        "dob": "2002-04-10",
        "gender": "Female",
        "district": "Pune",
        "current_location": "Hadapsar",
        "phone": new_phone(),
        "preferred_contact": "SMS",
        "consent_given": True,
    }
    payload.update(overrides)
    res = admin.post("/api/trainees", json=payload)
    assert res.status_code == 201, res.text
    return res.json()["trainee_id"]


def make_training(trainee_id: str, **overrides) -> str:
    payload = {
        "course_name": "Electrician",
        "provider_name": "ITI Pune",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "status": "Completed",
    }
    payload.update(overrides)
    res = admin.post(f"/api/trainees/{trainee_id}/training-records", json=payload)
    assert res.status_code == 201, res.text
    assert res.json()["trainee_id"] == trainee_id
    return res.json()["record_id"]


def make_outcome(trainee_id: str, training_id: str, outcome_type: str, status_date="2025-05-01") -> str:
    res = admin.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "outcome_type": outcome_type,
            "status_date": status_date,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["trainee_id"], body["training_id"], body["outcome_type"]) == (
        trainee_id,
        training_id,
        outcome_type,
    )
    return body["outcome_id"]


def make_employment(trainee_id: str, outcome_id: str, **overrides) -> str:
    payload = {
        "outcome_id": outcome_id,
        "trainee_id": trainee_id,
        "company_name": "Volt Works Pvt Ltd",
        "job_role": "Junior Electrician",
        "joining_date": "2025-05-15",
    }
    payload.update(overrides)
    res = admin.post("/api/employment", json=payload)
    assert res.status_code == 201, res.text
    assert res.json()["outcome_id"] == outcome_id
    return res.json()["employment_id"]


def add_wage(trainee_id, employment_id, salary, period, effective_date):
    res = admin.post(
        "/api/wage-history",
        json={
            "employment_id": employment_id,
            "trainee_id": trainee_id,
            "salary": salary,
            "salary_period": period,
            "effective_date": effective_date,
            "source": "Employer",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def add_status(trainee_id, employment_id, status, status_date, reason=None):
    res = admin.post(
        "/api/employment-status",
        json={
            "employment_id": employment_id,
            "trainee_id": trainee_id,
            "employment_status": status,
            "status_date": status_date,
            "reason": reason,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def get_ok(client, path, **kwargs):
    res = client.get(path, **kwargs)
    assert res.status_code == 200, f"{path}: {res.status_code} {res.text}"
    return res.json()


# =====================================================================
# 1. Access control
# =====================================================================


def _concrete(path: str) -> str:
    return path.replace("{", "").replace("}", "")


def test_every_non_public_route_requires_authentication(isolated_db):
    public = {"/", "/api/system/health", "/api/auth/token",
              "/api/self-report/{token}", "/api/self-report/{token}/contact", "/api/employer-verify/{token}"}
    checked = 0
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or route.path in public or not route.path.startswith("/api/"):
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            res = anon.request(method, _concrete(route.path))
            assert res.status_code == 401, f"{method} {route.path} -> {res.status_code}"
            checked += 1
    assert checked > 60


def test_analyst_can_read_aggregates_but_not_personal_records(isolated_db):
    trainee_id = make_trainee()

    for path in AGGREGATE_ENDPOINTS:
        assert analyst.get(path).status_code == 200, path

    forbidden = [
        ("get", f"/api/trainees/{trainee_id}"),
        ("get", f"/api/trainees/{trainee_id}/contact"),
        ("get", f"/api/trainees/{trainee_id}/training-records"),
        ("get", f"/api/trainees/{trainee_id}/employment-history"),
        ("get", "/api/followups/pending"),
        ("post", "/api/wage-history"),
        ("post", "/api/trainees"),
    ]
    for method, path in forbidden:
        assert getattr(analyst, method)(path).status_code == 403, path


def test_login_and_token_validation(isolated_db):
    username, password = TEST_USERS["admin"]
    res = anon.post("/api/auth/token", data={"username": username, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert res.json()["role"] == "admin"

    me = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"username": username, "role": "admin"}

    bad = anon.post("/api/auth/token", data={"username": username, "password": "wrong"})
    assert bad.status_code == 401
    unknown = anon.post("/api/auth/token", data={"username": "nobody", "password": "x"})
    assert unknown.status_code == 401

    import os

    secret = os.environ["JWT_SECRET_KEY"]
    expired = jwt.encode(
        {"sub": username, "role": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        secret,
        algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": username, "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "some-other-secret-key-that-is-long-enough-000",
        algorithm="HS256",
    )
    escalated = jwt.encode(  # analyst account claiming the admin role
        {"sub": TEST_USERS["analyst"][0], "role": "admin",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        secret,
        algorithm="HS256",
    )
    for bad_token in (expired, forged, escalated, "not-a-jwt"):
        res = anon.get("/api/analytics/overview", headers={"Authorization": f"Bearer {bad_token}"})
        assert res.status_code == 401


def test_auth_fails_closed_without_secret(isolated_db, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    username, password = TEST_USERS["admin"]
    assert anon.post(
        "/api/auth/token", data={"username": username, "password": password}
    ).status_code == 503
    assert admin.get("/api/analytics/overview").status_code == 503


def test_health_and_docs_are_public():
    assert anon.get("/").status_code == 200
    assert anon.get("/docs").status_code == 200
    schema = anon.get("/openapi.json").json()
    assert "/api/auth/token" in schema["paths"]
    assert "OAuth2PasswordBearer" in schema["components"]["securitySchemes"]


# =====================================================================
# 2. Consent, stable identity, contact updates
# =====================================================================


def test_consent_is_required_and_never_assumed(isolated_db):
    base = {
        "full_name": "Consent Check",
        "dob": "2001-01-01",
        "gender": "Male",
        "district": "Nashik",
        "preferred_contact": "Phone",
    }
    assert admin.post("/api/trainees", json={**base, "phone": new_phone(), "consent_given": False}).status_code == 422
    assert admin.post("/api/trainees", json={**base, "phone": new_phone()}).status_code == 422
    refused = {**base, "phone": new_phone(), "consent_given": True, "consent_analytics": False}
    assert admin.post("/api/trainees", json=refused).status_code == 422

    trainee_id = make_trainee()
    profile = get_ok(admin, f"/api/trainees/{trainee_id}")
    assert profile["consent_given"] is True
    for field in ("phone", "email", "dob"):
        assert field not in profile


def test_withdrawn_consent_blocks_new_followups_and_contact(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(trainee_id)

    res = admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": False})
    assert res.status_code == 200 and res.json()["consent_given"] is False
    assert admin.post(f"/api/followups/generate/{training_id}").status_code == 409

    admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": True})
    assert admin.post(f"/api/followups/generate/{training_id}").json()["followups_created"] == 4
    followup_id = get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"][0]["followup_id"]

    admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": False})
    attempt = admin.post(
        f"/api/followups/{followup_id}/attempt",
        json={"attempt_date": "2025-05-01", "contact_method": "Phone", "attempt_status": "Successful"},
    )
    assert attempt.status_code == 409
    # History is kept, not deleted
    assert len(get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]) == 4


def test_contact_update_keeps_stable_identity(isolated_db):
    trainee_id = make_trainee()
    other_phone = new_phone()
    make_trainee(phone=other_phone)

    new_number = new_phone()
    res = admin.patch(
        f"/api/trainees/{trainee_id}",
        json={"phone": f"+91 {new_number}", "current_location": "Nagpur", "email": "moved@example.com"},
    )
    assert res.status_code == 200
    assert res.json()["trainee_id"] == trainee_id
    contact = get_ok(admin, f"/api/trainees/{trainee_id}/contact")
    assert (contact["phone"], contact["current_location"], contact["email"]) == (
        new_number, "Nagpur", "moved@example.com",
    )

    assert admin.patch(f"/api/trainees/{trainee_id}", json={"phone": other_phone}).status_code == 409
    assert admin.patch(f"/api/trainees/{trainee_id}", json={"phone": None}).status_code == 422
    assert admin.patch(f"/api/trainees/{trainee_id}", json={"phone": "12345"}).status_code == 422


def test_training_programme_and_assessment_status(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(
        trainee_id, program_name="PMKVY 4.0", assessment_score=72, assessment_status="passed"
    )
    record = get_ok(admin, f"/api/training/{training_id}")
    assert (record["program_name"], record["assessment_status"], record["assessment_score"]) == (
        "PMKVY 4.0", "Passed", 72.0,
    )
    bad = admin.post(
        f"/api/trainees/{trainee_id}/training-records",
        json={"course_name": "Welding", "provider_name": "ITI", "start_date": "2025-01-01",
              "assessment_status": "Maybe"},
    )
    assert bad.status_code == 422
    assert admin.patch(f"/api/training-records/{training_id}", json={"status": None}).status_code == 422


# =====================================================================
# 3. End-to-end journey (exact values)
# =====================================================================


def test_end_to_end_journey(isolated_db):
    # Trainee + consent
    trainee_id = make_trainee(full_name="Aarav Patil", email="aarav@example.com")
    profile = get_ok(admin, f"/api/trainees/{trainee_id}")
    assert profile["trainee_id"] == trainee_id and profile["consent_given"] is True

    # Training -> attendance -> assessment -> certification
    training_id = make_training(
        trainee_id, program_name="PMKVY 4.0", status="Ongoing", end_date=None,
        attendance_percentage=88.5,
    )
    patched = admin.patch(
        f"/api/training-records/{training_id}",
        json={
            "status": "Completed",
            "end_date": "2025-03-31",
            "assessment_score": 81,
            "assessment_status": "Passed",
            "certification_issued": True,
            "certification_id": "CERT-ELEC-0001",
        },
    ).json()
    assert patched["record_id"] == training_id and patched["trainee_id"] == trainee_id
    assert (patched["attendance_percentage"], patched["assessment_score"]) == (88.5, 81.0)
    assert patched["certification_issued"] is True
    assert get_ok(admin, f"/api/trainees/{trainee_id}/training")[0]["record_id"] == training_id

    # Follow-up generation: calendar-correct dates, all linked to this training
    assert admin.post(f"/api/followups/generate/{training_id}").json()["followups_created"] == 4
    timeline = get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]
    assert {f["followup_type"]: f["scheduled_date"] for f in timeline} == {
        "30_DAY": "2025-04-30",
        "90_DAY": "2025-06-29",
        "6_MONTH": "2025-09-30",
        "12_MONTH": "2026-03-31",
    }
    assert all(f["training_id"] == training_id for f in timeline)
    fup_30 = next(f["followup_id"] for f in timeline if f["followup_type"] == "30_DAY")

    # Assisted follow-up: two contact attempts, then completion with outcome
    for status in ("No Response", "Successful"):
        res = admin.post(
            f"/api/followups/{fup_30}/attempt",
            json={"attempt_date": "2025-05-02", "contact_method": "Phone", "attempt_status": status},
        )
        assert res.status_code == 201 and res.json()["followup_id"] == fup_30
    admin.post(
        f"/api/followups/{fup_30}/outcome-update",
        json={"employment_status": "Employed", "training_relevance": 4,
              "skill_gap": True, "additional_training_needed": True},
    )
    outcome_id = make_outcome(trainee_id, training_id, "Employed", "2025-05-01")
    done = admin.post(
        f"/api/followups/{fup_30}/complete",
        json={"completed_date": "2025-05-02", "outcome_id": outcome_id},
    )
    assert done.status_code == 200 and done.json()["status"] == "Completed"
    assert get_ok(admin, f"/api/followups/{fup_30}")["outcome_id"] == outcome_id
    fsum = get_ok(admin, f"/api/followups/{fup_30}/summary")
    assert fsum["attempt_count"] == 2 and fsum["latest_attempt"]["attempt_status"] == "Successful"
    assert fsum["current_outcome"]["training_relevance"] == 4

    # Employment -> employer verification -> wage history -> status history
    employment_id = make_employment(trainee_id, outcome_id, salary=20000)
    ver = admin.post(
        "/api/employer-verifications",
        json={"employment_id": employment_id, "trainee_id": trainee_id,
              "employer_name": "Volt Works Pvt Ltd", "employer_contact": "hr@voltworks.example",
              "verification_status": "Verified", "verification_method": "Employer Contact",
              "verified_date": "2025-06-01", "verified_by": "Officer K"},
    )
    assert ver.status_code == 201
    latest_ver = get_ok(admin, f"/api/employment/{employment_id}/verification")
    assert latest_ver["verification_id"] == ver.json()["verification_id"]
    assert (latest_ver["employment_id"], latest_ver["trainee_id"]) == (employment_id, trainee_id)

    add_wage(trainee_id, employment_id, 20000, "Monthly", "2025-05-15")
    add_wage(trainee_id, employment_id, 25000, "Monthly", "2025-11-15")
    add_status(trainee_id, employment_id, "Active", "2025-05-15")

    summary = get_ok(admin, f"/api/employment/{employment_id}/summary")
    assert summary["verification"] == {"status": "Verified", "method": "Employer Contact"}
    assert summary["current_status"] == "Active"
    assert summary["salary"]["growth_percentage"] == 25.0
    history = get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"]
    assert [h["employment_id"] for h in history] == [employment_id]

    # Analytics
    overview = get_ok(analyst, "/api/analytics/overview")
    assert overview["total_trainees"] == 1 and overview["completed_trainings"] == 1
    assert overview["employed_trainees"] == 1
    assert (overview["placement_rate"], overview["employment_rate"], overview["retention_rate"]) == (100.0, 100.0, 100.0)
    wages = get_ok(analyst, "/api/analytics/wage-progression")
    assert (wages["average_initial_salary"], wages["average_latest_salary"]) == (20000.0, 25000.0)
    assert wages["average_salary_growth_percentage"] == 25.0
    assert get_ok(analyst, "/api/analytics/training-relevance")["average_relevance"] == 4.0
    course = get_ok(analyst, "/api/analytics/course-performance")
    assert course == [{"course_name": "Electrician", "total_trainees": 1, "completed": 1, "placed": 1,
                       "employed": 1, "self_employed": 0, "apprenticeship": 0, "unemployed": 0,
                       "placement_rate": 100.0}]

    # Insights
    insight_summary = get_ok(analyst, "/api/insights/summary")["metrics"]
    assert insight_summary["placement_rate"] == 100.0
    assert insight_summary["skill_gap_percentage"] == 100.0
    assert insight_summary["followup_completion_rate"] == 25.0  # 1 of 4 follow-ups done
    longitudinal = get_ok(analyst, "/api/insights/longitudinal-outcomes")
    assert longitudinal["training_completed"] == 1
    assert longitudinal["30_day_followups_completed"] == 1
    assert (longitudinal["employed_trainees"], longitudinal["retained_trainees"]) == (1, 1)
    quality = get_ok(analyst, "/api/insights/data-quality")
    assert quality["employment_without_wage_history"] == 0
    assert quality["employment_without_verification"] == 0
    assert quality["employment_without_status_history"] == 0
    assert quality["completed_training_without_outcome"] == 0
    areas = {a["area"] for a in get_ok(analyst, "/api/insights/remedial-actions")}
    assert "Skill Development" in areas  # triggered by the recorded skill gap


# =====================================================================
# 4. Outcome types and the placement definition
# =====================================================================


def test_all_outcome_types_and_placement_definition(isolated_db):
    ids = {}
    for outcome_type in ("Employed", "Self-employed", "Apprenticeship",
                         "Unemployed", "Further Education", "Not Reachable"):
        trainee_id = make_trainee()
        training_id = make_training(trainee_id)
        ids[outcome_type] = (trainee_id, make_outcome(trainee_id, training_id, outcome_type))

    t, o = ids["Self-employed"]
    assert admin.post("/api/self-employment", json={
        "outcome_id": o, "trainee_id": t, "business_name": "Spark Repairs",
        "business_type": "Electrical repair", "start_date": "2025-05-10", "monthly_income": 18000,
    }).status_code == 201
    t, o = ids["Apprenticeship"]
    assert admin.post("/api/apprenticeships", json={
        "outcome_id": o, "trainee_id": t, "organization_name": "MSEB",
        "role": "Apprentice Lineman", "start_date": "2025-05-10", "monthly_stipend": 9000,
    }).status_code == 201
    t, o = ids["Unemployed"]
    assert admin.post("/api/non-placement", json={
        "outcome_id": o, "trainee_id": t, "reason_category": "Lack of Jobs",
    }).status_code == 201
    # Detail records must match their outcome type
    t, o = ids["Unemployed"]
    assert admin.post("/api/employment", json={
        "outcome_id": o, "trainee_id": t, "company_name": "X Ltd",
        "job_role": "Helper", "joining_date": "2025-05-10",
    }).status_code == 400

    placement = get_ok(analyst, "/api/analytics/placement-rate")
    assert placement == {"eligible_trainees": 6, "placed_trainees": 3, "placement_rate": 50.0}
    employment = get_ok(analyst, "/api/analytics/employment-rate")
    assert (employment["employed_trainees"], employment["employment_rate"]) == (1, 16.67)

    overview = get_ok(analyst, "/api/analytics/overview")
    for key in ("employed_trainees", "self_employed_trainees", "apprenticeship_trainees",
                "unemployed_trainees", "further_education_trainees", "not_reachable_trainees"):
        assert overview[key] == 1, key
    assert overview["placed_trainees"] == 3

    gender = get_ok(analyst, "/api/analytics/demographics")["gender_distribution"]
    assert gender[0]["completed_trainees"] == 6 and gender[0]["placement_rate"] == 50.0
    reasons = get_ok(analyst, "/api/insights/non-placement")
    assert reasons["most_frequent_reason"] == "Lack of Jobs"


def test_latest_outcome_per_training_is_used(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(trainee_id)
    make_outcome(trainee_id, training_id, "Unemployed", "2025-05-01")
    make_outcome(trainee_id, training_id, "Employed", "2025-09-01")

    placement = get_ok(analyst, "/api/analytics/placement-rate")
    assert placement == {"eligible_trainees": 1, "placed_trainees": 1, "placement_rate": 100.0}
    overview = get_ok(analyst, "/api/analytics/overview")
    assert overview["total_training_records"] == 1
    assert overview["unemployed_trainees"] == 0
    # Both outcomes are still stored — history is not overwritten
    assert len(get_ok(admin, f"/api/trainees/{trainee_id}/outcomes")["outcomes"]) == 2


# =====================================================================
# 5. Longitudinal wage + status history
# =====================================================================


def test_longitudinal_mixed_period_wages_and_attrition(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(trainee_id)
    outcome_id = make_outcome(trainee_id, training_id, "Employed")
    employment_id = make_employment(trainee_id, outcome_id)

    # Entered out of order on purpose: chronology must come from effective_date
    add_wage(trainee_id, employment_id, 300000, "Annual", "2026-01-01")
    add_wage(trainee_id, employment_id, 20000, "Monthly", "2025-05-15")
    add_wage(trainee_id, employment_id, 25000, "Monthly", "2025-11-15")
    add_status(trainee_id, employment_id, "Active", "2025-05-15")
    add_status(trainee_id, employment_id, "Left Job", "2026-03-01", reason="Relocation")

    wages = get_ok(admin, f"/api/employment/{employment_id}/wage-history")["wage_history"]
    assert [(w["salary"], w["salary_period"], w["effective_date"]) for w in wages] == [
        (20000.0, "Monthly", "2025-05-15"),
        (25000.0, "Monthly", "2025-11-15"),
        (300000.0, "Annual", "2026-01-01"),  # stored value untouched
    ]
    statuses = get_ok(admin, f"/api/employment/{employment_id}/status-history")["status_history"]
    assert [s["employment_status"] for s in statuses] == ["Active", "Left Job"]

    summary = get_ok(admin, f"/api/employment/{employment_id}/summary")
    assert summary["current_status"] == "Left Job"
    assert (summary["wage_history_count"], summary["status_history_count"]) == (3, 2)
    assert summary["salary"] == {
        "initial": 20000.0, "latest": 300000.0, "period": "Annual", "initial_period": "Monthly",
        "initial_monthly": 20000.0, "latest_monthly": 25000.0, "growth_percentage": 25.0,
    }

    progression = get_ok(analyst, "/api/analytics/wage-progression")
    assert progression["average_initial_salary"] == 20000.0
    assert progression["average_latest_salary"] == 25000.0
    assert progression["average_salary_change"] == 5000.0
    assert progression["average_salary_growth_percentage"] == 25.0
    assert progression["employment_records_with_wage_progression"] == 1

    assert get_ok(analyst, "/api/analytics/retention-rate")["retention_rate"] == 0.0
    attrition = get_ok(analyst, "/api/analytics/attrition")
    assert (attrition["attrition_records"], attrition["attrition_rate"]) == (1, 100.0)
    assert attrition["reasons"] == [{"reason": "Relocation", "count": 1}]
    course = get_ok(analyst, "/api/insights/accountability")["courses"][0]
    assert (course["attrition_rate"], course["average_salary_growth_percentage"]) == (100.0, 25.0)


@pytest.mark.parametrize(
    "records, expected_initial, expected_latest, expected_growth",
    [
        ([(20000, "Monthly", 1), (22000, "Monthly", 2)], 20000, 22000, 10.0),  # M -> M
        ([(240000, "Annual", 1), (300000, "Annual", 2)], 20000, 25000, 25.0),  # A -> A
        ([(20000, "Monthly", 1), (300000, "Annual", 2)], 20000, 25000, 25.0),  # M -> A
        ([(240000, "Annual", 1), (25000, "Monthly", 2)], 20000, 25000, 25.0),  # A -> M
        ([(25000, "Monthly", 3), (20000, "Monthly", 1), (300000, "Annual", 2)], 20000, 25000, 25.0),
        ([(20000, "Monthly", 1)], 20000, 20000, None),  # one record: no progression
        ([(0, "Monthly", 1), (20000, "Monthly", 2)], 0, 20000, None),  # growth from 0 undefined
        ([(20000, "Weekly", 1), (22000, "Monthly", 2)], 22000, 22000, None),  # unknown period ignored
    ],
)
def test_wage_progression_normalisation(records, expected_initial, expected_latest, expected_growth):
    from datetime import date

    rows = [
        SimpleNamespace(salary=s, salary_period=p, effective_date=date(2025, 1, d), id=i)
        for i, (s, p, d) in enumerate(records)
    ]
    result = wage_progression_for(rows)
    assert result["initial_monthly"] == pytest.approx(expected_initial)
    assert result["latest_monthly"] == pytest.approx(expected_latest)
    if expected_growth is None:
        assert result["growth_percentage"] is None
    else:
        assert result["growth_percentage"] == pytest.approx(expected_growth)


def test_wage_progression_without_wages():
    assert wage_progression_for([]) is None


def test_phase3_left_status_counts_as_attrition(isolated_db):
    trainee_id = make_trainee()
    outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
    make_employment(trainee_id, outcome_id, employment_status="Left")
    assert get_ok(analyst, "/api/analytics/attrition")["attrition_rate"] == 100.0
    assert get_ok(analyst, "/api/analytics/retention-rate")["retention_rate"] == 0.0


# =====================================================================
# 6. Follow-up idempotence
# =====================================================================


def test_followup_generation_is_idempotent(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(trainee_id)

    first = admin.post(f"/api/followups/generate/{training_id}").json()
    second = admin.post(f"/api/followups/generate/{training_id}").json()
    assert first["followups_created"] == 4
    assert second["followups_created"] == 0 and "already exists" in second["message"]
    timeline = get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]
    assert sorted(f["followup_type"] for f in timeline) == ["12_MONTH", "30_DAY", "6_MONTH", "90_DAY"]

    manual = admin.post("/api/followups", json={
        "trainee_id": trainee_id, "training_id": training_id,
        "followup_type": "30_DAY", "scheduled_date": "2025-05-05",
    })
    assert manual.status_code == 409
    assert get_ok(admin, "/api/followups/summary")["total"] == 4

    ongoing = make_training(trainee_id, status="Ongoing", end_date=None)
    assert admin.post(f"/api/followups/generate/{ongoing}").status_code == 400


# =====================================================================
# 7. Empty database
# =====================================================================


def test_every_aggregate_endpoint_on_empty_database(isolated_db):
    for path in AGGREGATE_ENDPOINTS:
        assert analyst.get(path).status_code == 200, path

    overview = get_ok(analyst, "/api/analytics/overview")
    assert all(value == 0 for value in overview.values())
    wages = get_ok(analyst, "/api/analytics/wage-progression")
    assert wages["employment_records"] == 0
    for key in ("average_initial_salary", "average_latest_salary",
                "average_salary_change", "average_salary_growth_percentage"):
        assert wages[key] is None, key
    assert get_ok(analyst, "/api/analytics/training-relevance")["average_relevance"] is None
    for path in ("/api/analytics/course-performance", "/api/analytics/cohort",
                 "/api/analytics/non-placement-reasons", "/api/analytics/remedial-insights",
                 "/api/insights/remedial-actions", "/api/insights/skill-gaps/by-course"):
        assert get_ok(analyst, path) == [], path
    assert get_ok(analyst, "/api/insights/accountability") == {"courses": [], "providers": []}
    summary = get_ok(analyst, "/api/insights/summary")
    assert summary["insights"] == []
    assert summary["metrics"]["top_non_placement_reason"] is None
    assert summary["metrics"]["average_training_relevance"] is None
    assert summary["metrics"]["average_salary_growth_percentage"] is None
    assert get_ok(analyst, "/api/analytics/attrition")["attrition_rate"] == 0.0


def test_database_error_returns_503_not_zeros(isolated_db):
    class BrokenSession:
        info: dict = {}

        def query(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

        def close(self):
            pass

    def broken():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken
    assert analyst.get("/api/analytics/placement-rate").status_code == 503
    assert analyst.get("/api/insights/summary").status_code == 503


# =====================================================================
# 8. Partial / incomplete data
# =====================================================================


def test_partial_data_stays_missing(isolated_db):
    make_trainee(current_location=None)                              # no training
    make_training(make_trainee(), status="Ongoing", end_date=None)   # training, not completed
    make_training(make_trainee())                                    # completed, no outcome
    t4 = make_trainee()
    make_outcome(t4, make_training(t4), "Employed")                  # outcome, no employment
    t5 = make_trainee()
    make_employment(t5, make_outcome(t5, make_training(t5), "Employed"))  # no wage/verification/status
    t6 = make_trainee()
    admin.post(f"/api/followups/generate/{make_training(t6)}")       # follow-ups, none completed

    # Missing demographic data (gender blank) inserted directly
    session = isolated_db()
    session.add(models.Trainee(
        trainee_id="TRN999999", full_name="Legacy Row", dob=datetime(1999, 1, 1).date(),
        gender=" ", district="Pune", phone="9000000001", preferred_contact="SMS", consent_given=True,
    ))
    session.commit()
    session.close()

    for path in AGGREGATE_ENDPOINTS:
        assert analyst.get(path).status_code == 200, path

    # Completed trainings = t3, t4, t5, t6. Only t4/t5 have a placement outcome;
    # missing outcomes are neither placed nor unemployed.
    placement = get_ok(analyst, "/api/analytics/placement-rate")
    assert placement == {"eligible_trainees": 4, "placed_trainees": 2, "placement_rate": 50.0}
    assert get_ok(analyst, "/api/analytics/overview")["unemployed_trainees"] == 0

    wages = get_ok(analyst, "/api/analytics/wage-progression")
    assert (wages["employment_records"], wages["employment_records_with_wage_data"]) == (1, 0)
    assert wages["average_salary_growth_percentage"] is None

    quality = get_ok(analyst, "/api/insights/data-quality")
    assert quality["completed_training_without_outcome"] == 2
    assert quality["employment_without_wage_history"] == 1
    assert quality["employment_without_verification"] == 1
    assert quality["employment_without_status_history"] == 1
    assert quality["trainees_missing_location"] == 2
    assert quality["trainees_missing_gender"] == 1
    assert (quality["followups_not_completed"], quality["followup_completion_rate"]) == (4, 0.0)

    genders = {g["gender"] for g in get_ok(analyst, "/api/analytics/demographics")["gender_distribution"]}
    assert genders == {"Female", "Unknown"}
    assert get_ok(analyst, "/api/analytics/skill-gaps")["skill_gap_percentage"] == 0.0
    assert get_ok(analyst, "/api/insights/skill-gaps")["average_training_relevance"] is None


# =====================================================================
# 9. Privacy of aggregate endpoints
# =====================================================================


def test_aggregate_endpoints_expose_no_personal_data(isolated_db):
    phone = new_phone()
    trainee_id = make_trainee(
        full_name="Zorawar Uniquename", phone=phone, email="zorawar.private@example.com", dob="1998-07-23",
    )
    outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
    employment_id = make_employment(trainee_id, outcome_id, company_name="Private Employer Co")
    admin.post("/api/employer-verifications", json={
        "employment_id": employment_id, "trainee_id": trainee_id, "employer_name": "Private Employer Co",
        "employer_contact": "+91-98989-12345 boss@private.example", "verification_status": "Verified",
        "verification_method": "Employer Contact",
    })
    add_wage(trainee_id, employment_id, 23456, "Monthly", "2025-06-01")

    sensitive = [phone, "zorawar.private@example.com", "1998-07-23", trainee_id, "Zorawar",
                 "boss@private.example", "98989-12345", employment_id, outcome_id]
    for path in AGGREGATE_ENDPOINTS:
        body = analyst.get(path).text
        for value in sensitive:
            assert value not in body, f"{path} exposes {value!r}"


@pytest.mark.parametrize(
    "raw, stored",
    [
        ("9123456701", "9123456701"),      # a real number that starts with 91
        ("+91 9123456701", "9123456701"),
        ("919123456701", "9123456701"),
        ("09123456701", "9123456701"),
        ("98765-43210", "9876543210"),
    ],
)
def test_phone_numbers_starting_with_91_are_valid(isolated_db, raw, stored):
    trainee_id = make_trainee(phone=raw)
    assert get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"] == stored
