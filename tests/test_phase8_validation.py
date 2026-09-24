"""
Phase 8 — Final Integration & SIH Validation Test Suite.

Validates:
1. End-to-end 15-step trainee journey (Trainee -> Consent -> Training -> Assessment -> Certification ->
   Follow-ups -> Complete Follow-up -> Outcome -> Employment -> Employer Verification ->
   Wage History -> Status History -> Analytics -> Insights).
2. All outcome types: Employed, Self-employed, Apprenticeship, Unemployed, Further Education, Not Reachable.
3. Longitudinal wage progression & job retention timeline (records preserved, chronological ordering).
4. Follow-up generation idempotence (duplicate prevention).
5. Safe handling of empty/incomplete edge cases (no crashes, no division by zero).
6. System health, OpenAPI/Swagger docs, and route registrations.
"""

import uuid
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def random_phone(prefix: str = "95") -> str:
    return f"{prefix}{uuid.uuid4().int % 100000000:08d}"


def create_test_trainee(phone_prefix: str = "95", **overrides) -> str:
    payload = {
        "full_name": "SIH Validation Trainee",
        "dob": "2001-08-15",
        "gender": "Female",
        "district": "Solapur",
        "current_location": "Solapur City",
        "phone": random_phone(phone_prefix),
        "email": f"trainee_{uuid.uuid4().hex[:8]}@example.com",
        "preferred_contact": "SMS",
        "consent_given": True,
    }
    payload.update(overrides)
    res = client.post("/api/trainees", json=payload)
    assert res.status_code == 201
    return res.json()["trainee_id"]


# =====================================================================
# 1. End-to-End 15-Step Journey
# =====================================================================


def test_end_to_end_trainee_journey():
    # Step 1: Create trainee
    trainee_id = create_test_trainee("94", full_name="Aarav Sharma")
    assert trainee_id.startswith("TRN")

    # Step 2: Record & verify consent
    profile = client.get(f"/api/trainees/{trainee_id}").json()
    assert profile["trainee_id"] == trainee_id
    assert profile["consent_given"] is True

    # Step 3: Create training
    training_payload = {
        "course_name": "Full Stack Web Development",
        "provider_name": "Maharashtra Skill Center",
        "start_date": "2025-01-01",
        "end_date": "2025-04-01",
        "status": "Ongoing",
        "attendance_percentage": 90.0,
        "assessment_score": 85.0,
        "certification_issued": False,
    }
    tr_res = client.post(f"/api/trainees/{trainee_id}/training-records", json=training_payload)
    assert tr_res.status_code == 201
    training_id = tr_res.json()["record_id"]
    assert training_id.startswith("TRC")

    # Also verify the standalone alias endpoint GET /api/training/{record_id}
    tr_alias = client.get(f"/api/training/{training_id}")
    assert tr_alias.status_code == 200
    assert tr_alias.json()["record_id"] == training_id

    # Step 4, 5, 6: Mark training completed, record assessment, issue certification
    patch_res = client.patch(
        f"/api/training-records/{training_id}",
        json={
            "status": "Completed",
            "attendance_percentage": 95.0,
            "assessment_score": 92.0,
            "certification_issued": True,
            "certification_id": f"CERT-FSWD-{uuid.uuid4().hex[:6].upper()}",
        },
    )
    assert patch_res.status_code == 200
    completed_tr = patch_res.json()
    assert completed_tr["status"] == "Completed"
    assert completed_tr["certification_issued"] is True
    assert completed_tr["assessment_score"] == 92.0

    # Step 7: Generate follow-ups
    gen_res = client.post(f"/api/followups/generate/{training_id}")
    assert gen_res.status_code == 200
    assert gen_res.json()["followups_created"] == 4

    # Verify follow-ups timeline for trainee
    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline").json()
    assert len(timeline["followups"]) == 4
    followup_types = {f["followup_type"] for f in timeline["followups"]}
    assert followup_types == {"30_DAY", "90_DAY", "6_MONTH", "12_MONTH"}

    # Step 8: Complete a follow-up (30_DAY)
    fup_30 = next(f for f in timeline["followups"] if f["followup_type"] == "30_DAY")
    comp_res = client.post(
        f"/api/followups/{fup_30['followup_id']}/complete",
        json={
            "completed_date": date.today().isoformat(),
            "notes": "Trainee successfully contacted via phone.",
        },
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "Completed"

    # Log contact attempt
    att_res = client.post(
        f"/api/followups/{fup_30['followup_id']}/attempt",
        json={
            "attempt_date": date.today().isoformat(),
            "contact_method": "Phone",
            "attempt_status": "Successful",
            "notes": "Phone conversation with trainee.",
        },
    )
    assert att_res.status_code == 201

    # Log outcome update on follow-up
    update_res = client.post(
        f"/api/followups/{fup_30['followup_id']}/outcome-update",
        json={
            "trainee_id": trainee_id,
            "employment_status": "Employed",
            "training_relevance": 5,
            "skill_gap": False,
            "additional_training_needed": False,
            "notes": "Working in software company, very happy.",
        },
    )
    assert update_res.status_code == 201

    # Step 9: Create an outcome (Employed)
    outcome_payload = {
        "trainee_id": trainee_id,
        "training_id": training_id,
        "outcome_type": "Employed",
        "status_date": "2025-05-01",
        "notes": "Joined Tech Solutions Ltd",
    }
    out_res = client.post("/api/outcomes", json=outcome_payload)
    assert out_res.status_code == 201
    outcome_id = out_res.json()["outcome_id"]
    assert outcome_id.startswith("OUT")

    # Step 10: Create employment detail
    emp_payload = {
        "outcome_id": outcome_id,
        "trainee_id": trainee_id,
        "company_name": "Tech Solutions Pvt Ltd",
        "job_role": "Junior Software Engineer",
        "joining_date": "2025-05-15",
        "salary": 30000.0,
        "employment_status": "Active",
        "job_location": "Pune",
        "job_relevance": "Relevant",
    }
    emp_res = client.post("/api/employment", json=emp_payload)
    assert emp_res.status_code == 201
    employment_id = emp_res.json()["employment_id"]
    assert employment_id.startswith("EMP")

    # Step 11: Verify employer
    ver_payload = {
        "employment_id": employment_id,
        "trainee_id": trainee_id,
        "employer_name": "Tech Solutions Pvt Ltd",
        "employer_contact": "hr@techsolutions.example.com",
        "verification_status": "Verified",
        "verification_method": "Employer Contact",
        "verified_date": date.today().isoformat(),
        "verified_by": "Verification Officer P. Kulkarni",
        "verification_notes": "HR confirmed active employment status and salary.",
    }
    ver_res = client.post("/api/employer-verifications", json=ver_payload)
    assert ver_res.status_code == 201
    assert ver_res.json()["verification_status"] == "Verified"

    # Step 12: Add wage history (initial salary, then updated increment)
    wage1_res = client.post(
        "/api/wage-history",
        json={
            "employment_id": employment_id,
            "trainee_id": trainee_id,
            "salary": 30000.0,
            "salary_period": "Monthly",
            "effective_date": "2025-05-15",
            "source": "Employer",
            "verification_status": "Verified",
            "notes": "Starting offer confirmed by HR",
        },
    )
    assert wage1_res.status_code == 201

    wage2_res = client.post(
        "/api/wage-history",
        json={
            "employment_id": employment_id,
            "trainee_id": trainee_id,
            "salary": 35000.0,
            "salary_period": "Monthly",
            "effective_date": "2025-11-15",
            "source": "Employer",
            "verification_status": "Verified",
            "notes": "6-month performance appraisal hike",
        },
    )
    assert wage2_res.status_code == 201

    # Check wage history listing preserves chronological history
    wage_history = client.get(f"/api/employment/{employment_id}/wage-history").json()
    assert len(wage_history["wage_history"]) == 2
    assert wage_history["wage_history"][0]["salary"] == 30000.0
    assert wage_history["wage_history"][1]["salary"] == 35000.0

    # Step 13: Add employment status history
    st1 = client.post(
        "/api/employment-status",
        json={
            "employment_id": employment_id,
            "trainee_id": trainee_id,
            "employment_status": "Active",
            "status_date": "2025-05-15",
            "notes": "Joined successfully",
        },
    )
    assert st1.status_code == 201

    # Step 14: Run Analytics
    overview = client.get("/api/analytics/overview").json()
    assert overview["total_trainees"] > 0
    assert overview["total_training_records"] > 0
    assert overview["placement_rate"] >= 0

    wage_prog = client.get("/api/analytics/wage-progression").json()
    assert wage_prog["employment_records"] > 0
    assert wage_prog["average_initial_salary"] > 0

    # Step 15: Run Insights
    summary = client.get("/api/insights/summary").json()
    assert "metrics" in summary
    assert "placement_rate" in summary["metrics"]

    longitudinal = client.get("/api/insights/longitudinal-outcomes").json()
    assert longitudinal["training_completed"] > 0


# =====================================================================
# 2. All Outcome Types
# =====================================================================


def test_all_outcome_types():
    types = [
        "Employed",
        "Self-employed",
        "Apprenticeship",
        "Unemployed",
        "Further Education",
        "Not Reachable",
    ]

    for otype in types:
        trainee_id = create_test_trainee("93")
        # Add completed training
        tr_res = client.post(
            f"/api/trainees/{trainee_id}/training-records",
            json={
                "course_name": f"Course for {otype}",
                "provider_name": "Skill Provider",
                "start_date": "2025-02-01",
                "end_date": "2025-05-01",
                "status": "Completed",
                "certification_issued": True,
            },
        )
        assert tr_res.status_code == 201
        training_id = tr_res.json()["record_id"]

        # Record outcome
        out_res = client.post(
            "/api/outcomes",
            json={
                "trainee_id": trainee_id,
                "training_id": training_id,
                "outcome_type": otype,
                "status_date": "2025-06-01",
            },
        )
        assert out_res.status_code == 201
        outcome_id = out_res.json()["outcome_id"]

        # If unemployed, record non-placement reason
        if otype == "Unemployed":
            np_res = client.post(
                "/api/non-placement",
                json={
                    "outcome_id": outcome_id,
                    "trainee_id": trainee_id,
                    "reason_category": "Skill Gap",
                    "reason_details": "Needs advanced certification",
                },
            )
            assert np_res.status_code == 201

        # If self-employed, record detail
        elif otype == "Self-employed":
            sem_res = client.post(
                "/api/self-employment",
                json={
                    "outcome_id": outcome_id,
                    "trainee_id": trainee_id,
                    "business_name": "Aarav Repair Services",
                    "business_type": "Electronics Repair",
                    "start_date": "2025-06-15",
                    "monthly_income": 25000.0,
                    "location": "Solapur",
                },
            )
            assert sem_res.status_code == 201

        # If apprenticeship, record detail
        elif otype == "Apprenticeship":
            apr_res = client.post(
                "/api/apprenticeships",
                json={
                    "outcome_id": outcome_id,
                    "trainee_id": trainee_id,
                    "organization_name": "State Electric Board",
                    "role": "Apprentice Lineman",
                    "start_date": "2025-06-15",
                    "monthly_stipend": 12000.0,
                    "location": "Solapur",
                },
            )
            assert apr_res.status_code == 201


# =====================================================================
# 3. Longitudinal Wage & Retention Preservation
# =====================================================================


def test_longitudinal_wage_and_retention():
    trainee_id = create_test_trainee("92")
    tr = client.post(
        f"/api/trainees/{trainee_id}/training-records",
        json={
            "course_name": "CNC Operator",
            "provider_name": "Tata ITI",
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
            "status": "Completed",
            "certification_issued": True,
        },
    ).json()

    out = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": tr["record_id"],
            "outcome_type": "Employed",
            "status_date": "2024-07-01",
        },
    ).json()

    emp = client.post(
        "/api/employment",
        json={
            "outcome_id": out["outcome_id"],
            "trainee_id": trainee_id,
            "company_name": "Precision Engineering Ltd",
            "job_role": "CNC Technician",
            "joining_date": "2024-07-15",
            "salary": 18000.0,
            "employment_status": "Active",
        },
    ).json()
    emp_id = emp["employment_id"]

    # Initial wage
    w1 = client.post(
        "/api/wage-history",
        json={
            "employment_id": emp_id,
            "trainee_id": trainee_id,
            "salary": 18000.0,
            "salary_period": "Monthly",
            "effective_date": "2024-07-15",
            "source": "Document",
        },
    )
    assert w1.status_code == 201

    # Second wage point
    w2 = client.post(
        "/api/wage-history",
        json={
            "employment_id": emp_id,
            "trainee_id": trainee_id,
            "salary": 24000.0,
            "salary_period": "Monthly",
            "effective_date": "2025-01-15",
            "source": "Employer",
        },
    )
    assert w2.status_code == 201

    # Verify both records preserved
    history = client.get(f"/api/employment/{emp_id}/wage-history").json()
    assert len(history["wage_history"]) == 2
    assert history["wage_history"][0]["salary"] == 18000.0
    assert history["wage_history"][1]["salary"] == 24000.0

    # Status 1: Active
    s1 = client.post(
        "/api/employment-status",
        json={
            "employment_id": emp_id,
            "trainee_id": trainee_id,
            "employment_status": "Active",
            "status_date": "2024-07-15",
        },
    )
    assert s1.status_code == 201

    # Status 2: Left Job
    s2 = client.post(
        "/api/employment-status",
        json={
            "employment_id": emp_id,
            "trainee_id": trainee_id,
            "employment_status": "Left Job",
            "status_date": "2025-06-01",
            "reason": "Higher Studies",
        },
    )
    assert s2.status_code == 201

    # Check status history
    st_hist = client.get(f"/api/employment/{emp_id}/status-history").json()
    assert len(st_hist["status_history"]) == 2
    assert st_hist["status_history"][0]["employment_status"] == "Active"
    assert st_hist["status_history"][1]["employment_status"] == "Left Job"

    # Combined summary reflects latest status
    summary = client.get(f"/api/employment/{emp_id}/summary").json()
    assert summary["current_status"] == "Left Job"


# =====================================================================
# 4. Duplicate Prevention (Idempotence)
# =====================================================================


def test_followup_duplicates():
    trainee_id = create_test_trainee("88")
    tr = client.post(
        f"/api/trainees/{trainee_id}/training-records",
        json={
            "course_name": "Idempotence Course",
            "provider_name": "Test ITI",
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "status": "Completed",
            "certification_issued": True,
        },
    ).json()

    # First generation
    g1 = client.post(f"/api/followups/generate/{tr['record_id']}")
    assert g1.status_code == 200
    assert g1.json()["followups_created"] == 4

    # Second generation must not create duplicates
    g2 = client.post(f"/api/followups/generate/{tr['record_id']}")
    assert g2.status_code == 200
    assert g2.json()["followups_created"] == 0
    assert "already exists" in g2.json()["message"]


# =====================================================================
# 5. Empty and Incomplete Data Handling
# =====================================================================


def test_empty_and_incomplete_cases():
    # A. Trainee with no training
    t1 = create_test_trainee("90")
    t1_records = client.get(f"/api/trainees/{t1}/training-records").json()
    assert t1_records == []

    # B. Training exists with no outcome
    t2 = create_test_trainee("89")
    tr2 = client.post(
        f"/api/trainees/{t2}/training-records",
        json={
            "course_name": "Course Without Outcome",
            "provider_name": "Center",
            "start_date": "2025-01-01",
            "status": "Ongoing",
        },
    ).json()
    t2_outcomes = client.get(f"/api/trainees/{t2}/outcomes").json()
    assert t2_outcomes["outcomes"] == []

    # Filter with nonexistent district
    nonexistent = client.get("/api/analytics/overview", params={"district": "NonexistentCity999"}).json()
    assert nonexistent["total_trainees"] == 0
    assert nonexistent["placement_rate"] == 0.0

    # Non-placement analysis with non-crashing response
    non_placement_insights = client.get("/api/insights/non-placement").json()
    assert "total_records" in non_placement_insights

    # Attrition with no division by zero
    attrition = client.get("/api/analytics/attrition").json()
    assert 0.0 <= attrition["attrition_rate"] <= 100.0


# =====================================================================
# 6. Health & API Documentation
# =====================================================================


def test_system_health_and_docs():
    h_root = client.get("/")
    assert h_root.status_code == 200
    assert h_root.json()["status"] == "ok"
    assert h_root.json()["phase"] == 8

    h_sys = client.get("/api/system/health")
    assert h_sys.status_code == 200
    assert h_sys.json()["status"] == "ok"
    assert h_sys.json()["database"] == "connected"

    docs = client.get("/docs")
    assert docs.status_code == 200

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    assert schema["info"]["version"] == "8.0.0"

    paths = schema["paths"]
    # Check key Phase 1-8 paths
    assert "/api/trainees" in paths
    assert "/api/training" in paths
    assert "/api/outcomes" in paths
    assert "/api/employment" in paths
    assert "/api/self-employment" in paths
    assert "/api/apprenticeships" in paths
    assert "/api/non-placement" in paths
    assert "/api/followups/generate/{training_id}" in paths
    assert "/api/employer-verifications" in paths
    assert "/api/wage-history" in paths
    assert "/api/employment-status" in paths
    assert "/api/analytics/overview" in paths
    assert "/api/insights/summary" in paths
    assert "/api/system/health" in paths
