"""
Seed a realistic SIH26135 demo dataset through the real API.

    python scripts/seed_demo_data.py

- Goes through the same endpoints (and validation) as a real user, as
  the admin configured in .env, against DATABASE_URL.
- INSERTS ONLY. Never updates or deletes existing rows.
- Refuses to run twice (checks for the first demo Skill India ID).
- Deterministic (fixed random seed), so every run of a fresh database
  produces the same numbers.

What it creates (48 trainees in five districts that the automated tests
never used, so district-filtered analytics show only demo data):
  * 6 courses / providers under PMKVY 4.0, DDU-GKY and the State Skill
    Mission, each with a different outcome profile
  * enrolled / ongoing / dropped / completed trainings with attendance,
    assessment and certification
  * 30/90-day and 6/12-month follow-ups with contact attempts: completed,
    missed, not reachable, answered through self-report links, and some
    left due for the automated dispatcher
  * all six outcome types, including trainees who move from Unemployed
    to Employed between follow-ups
  * employer verification via the employer confirmation link, documents
    and still-pending trainee claims
  * wage history with raises (some annual CTC figures) and attrition
  * cross-programme IDs, one duplicate registration, two consent
    withdrawals
"""

import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from fastapi.testclient import TestClient  # noqa: E402

from database.connection import init_db  # noqa: E402
from main import app  # noqa: E402
from services.auth import PURPOSE_SELF_REPORT, create_access_token, create_link_token  # noqa: E402

TODAY = date.today()
RNG = random.Random(26135)
MARKER_TYPE, MARKER_PREFIX = "Skill India Digital ID", "SID-DEMO-"

DISTRICTS = [
    ("Nashik", ["Nashik Road", "Satpur", "Sinnar"]),
    ("Kolhapur", ["Ichalkaranji", "Karvir", "Gadhinglaj"]),
    ("Aurangabad", ["Waluj", "Paithan", "Cidco"]),
    ("Amravati", ["Badnera", "Achalpur", "Morshi"]),
    ("Latur", ["Udgir", "Ausa", "Nilanga"]),
]

# course, provider, programme, outcome weights (Emp, Self, Appr, Unemp, FurtherEd, NotReach),
# relevance mean, skill-gap probability, attrition probability, base monthly wage
COURSES = [
    ("Electrician", "Govt ITI Nashik", "PMKVY 4.0",
     (55, 10, 15, 10, 5, 5), 4.2, 0.15, 0.15, 15000),
    ("Solar PV Installer", "Suryamitra Skill Centre", "PMKVY 4.0",
     (45, 20, 10, 15, 5, 5), 3.9, 0.25, 0.20, 14000),
    ("Retail Sales Associate", "Retailers Skill Academy", "DDU-GKY",
     (50, 5, 0, 25, 5, 15), 3.1, 0.30, 0.45, 12000),
    ("Accounts Assistant (Tally)", "Kolhapur Computer Institute", "DDU-GKY",
     (40, 10, 5, 30, 10, 5), 2.6, 0.55, 0.25, 13000),
    ("Two-Wheeler Service Technician", "AutoSkills Training Centre", "PMKVY 4.0",
     (40, 35, 10, 10, 0, 5), 4.0, 0.20, 0.20, 13500),
    ("General Duty Assistant", "Arogya Skills Institute", "State Skill Mission",
     (60, 0, 10, 15, 10, 5), 3.7, 0.20, 0.35, 14500),
]
OUTCOME_TYPES = ["Employed", "Self-employed", "Apprenticeship", "Unemployed", "Further Education", "Not Reachable"]
EMPLOYERS = {
    "Electrician": ["Crompton Services Pvt Ltd", "Volt Works Pvt Ltd", "MahaElectric Contractors"],
    "Solar PV Installer": ["SunGrid Solar Pvt Ltd", "Tata Power Solar", "Surya Urja Installers"],
    "Retail Sales Associate": ["D-Mart", "Reliance Trends", "More Retail"],
    "Accounts Assistant (Tally)": ["Shree Traders", "Patil & Co. Chartered Accountants", "Kolhapur Sugar Co-op"],
    "Two-Wheeler Service Technician": ["Bajaj Service Point", "Hero MotoCorp Dealer", "TVS Authorised Workshop"],
    "General Duty Assistant": ["Ruby Care Hospital", "District Civil Hospital", "Sahyadri Nursing Home"],
}
ROLES = {
    "Electrician": ("Junior Electrician", "Electrical repair shop", "Apprentice Electrician"),
    "Solar PV Installer": ("Solar Technician", "Solar installation service", "Apprentice Solar Technician"),
    "Retail Sales Associate": ("Sales Associate", "Mobile accessories stall", "Retail Trainee"),
    "Accounts Assistant (Tally)": ("Accounts Assistant", "Bookkeeping service", "Accounts Apprentice"),
    "Two-Wheeler Service Technician": ("Service Technician", "Two-wheeler garage", "Apprentice Mechanic"),
    "General Duty Assistant": ("Patient Care Assistant", "Home care service", "Nursing Apprentice"),
}
NON_PLACEMENT_REASONS = ["Lack of Jobs", "Skill Gap", "Low Salary", "Location Problem",
                         "Personal/Family Reason", "Relocation Issue"]
ATTRITION_REASONS = ["Better opportunity", "Low salary", "Relocation", "Family reasons", "Work conditions"]
FEMALE = ["Priya", "Sneha", "Pooja", "Anjali", "Kavita", "Sayali", "Rutuja", "Ashwini", "Neha",
          "Shraddha", "Komal", "Pallavi", "Aarti", "Manisha", "Swati", "Dipali"]
MALE = ["Rahul", "Amit", "Sagar", "Vishal", "Akash", "Rohit", "Nikhil", "Ganesh", "Sachin",
        "Mahesh", "Omkar", "Pratik", "Suraj", "Tushar", "Yogesh", "Kunal"]
SURNAMES = ["Patil", "Jadhav", "Pawar", "Shinde", "Kulkarni", "More", "Deshmukh", "Gaikwad",
            "Chavan", "Kale", "Bhosale", "Sawant", "Shaikh", "Wagh", "Salunkhe", "Kamble"]


class Api:
    def __init__(self):
        token, _ = create_access_token(os.environ["ADMIN_USERNAME"], "admin")
        self.client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        self.calls = 0

    def request(self, method, path, expected=(200, 201), **kwargs):
        self.calls += 1
        res = self.client.request(method, path, **kwargs)
        if res.status_code not in expected:
            raise RuntimeError(f"{method} {path} -> {res.status_code}: {res.text[:300]}")
        return res.json() if res.content else None

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.request("POST", path, json=json, **kw)

    def patch(self, path, json=None, **kw):
        return self.request("PATCH", path, json=json, **kw)


def pick_weighted(weights):
    return RNG.choices(OUTCOME_TYPES, weights=weights, k=1)[0]


def new_phone():
    return f"{RNG.choice('6789')}{RNG.randint(0, 999_999_999):09d}"


def register(api, n, district, course):
    female = RNG.random() < 0.45
    first = RNG.choice(FEMALE if female else MALE)
    last = RNG.choice(SURNAMES)
    age = RNG.choice([18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 30, 33, 37, 41])
    dob = date(TODAY.year - age, RNG.randint(1, 12), RNG.randint(1, 28))
    preferred = RNG.choices(["SMS", "Phone", "Email"], weights=[55, 30, 15])[0]
    payload = {
        "full_name": f"{first} {last}",
        "dob": dob.isoformat(),
        "gender": "Female" if female else "Male",
        "district": district[0],
        "current_location": RNG.choice(district[1]),
        "preferred_contact": preferred,
        "consent_given": True,
        "consent_analytics": True,
        "consent_privacy_notice": True,
        "external_ids": [{"id_type": MARKER_TYPE, "id_value": f"{MARKER_PREFIX}{n:04d}",
                          "source_programme": course[2]}],
    }
    if preferred == "Email" or RNG.random() < 0.3:
        payload["email"] = f"{first.lower()}.{last.lower()}.{n}@example.com"
    for _ in range(5):  # retry on the (unlikely) phone clash
        payload["phone"] = new_phone()
        res = api.client.post("/api/trainees", json=payload)
        api.calls += 1
        if res.status_code == 201:
            return res.json()["trainee_id"], payload
        if res.status_code != 409:
            raise RuntimeError(f"register -> {res.status_code}: {res.text[:300]}")
    raise RuntimeError("could not find a free phone number")


def add_training(api, trainee_id, course, status, end):
    start = (end or TODAY) - timedelta(days=RNG.choice([75, 90, 105]))
    attendance = round(RNG.uniform(62, 99), 1)
    score = round(RNG.uniform(38, 96), 1) if status != "Dropped" else None
    passed = score is not None and score >= 50
    body = {
        "program_name": course[2],
        "course_name": course[0],
        "provider_name": course[1],
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "status": status,
        "attendance_percentage": attendance if status != "Enrolled" else None,
        "assessment_score": score if status == "Completed" else None,
        "assessment_status": ("Passed" if passed else "Failed") if status == "Completed" else "Pending",
        "certification_issued": status == "Completed" and passed,
    }
    if body["certification_issued"]:
        body["certification_id"] = f"CERT-{course[2].split()[0]}-{RNG.randint(100000, 999999)}"
    return api.post(f"/api/trainees/{trainee_id}/training-records", json=body)["record_id"]


def attempt(api, followup_id, when, status, method="Phone"):
    api.post(f"/api/followups/{followup_id}/attempt", json={
        "attempt_date": when.isoformat(), "contact_method": method, "attempt_status": status,
    })


def followup_update(api, fu, outcome_type, course, reason=None):
    relevance = max(1, min(5, round(RNG.gauss(course[4], 0.9))))
    api.post(f"/api/followups/{fu['followup_id']}/outcome-update", json={
        "employment_status": outcome_type,
        "training_relevance": relevance,
        "skill_gap": RNG.random() < course[5],
        "additional_training_needed": RNG.random() < course[5] + 0.1,
        "unemployment_reason_category": reason,
    })


def record_outcome(api, trainee_id, training_id, outcome_type, when, course, stats):
    outcome_id = api.post("/api/outcomes", json={
        "trainee_id": trainee_id, "training_id": training_id,
        "outcome_type": outcome_type, "status_date": when.isoformat(),
    })["outcome_id"]
    employer, (job_role, business, apprentice_role) = RNG.choice(EMPLOYERS[course[0]]), ROLES[course[0]]
    employment_id = None
    if outcome_type == "Employed":
        salary = round(course[7] * RNG.uniform(0.9, 1.25), -2)
        employment_id = api.post("/api/employment", json={
            "outcome_id": outcome_id, "trainee_id": trainee_id, "company_name": employer,
            "job_role": job_role, "joining_date": when.isoformat(), "salary": salary,
            "job_relevance": RNG.choice(["Relevant", "Relevant", "Partially Relevant"]),
        })["employment_id"]
        api.post("/api/wage-history", json={
            "employment_id": employment_id, "trainee_id": trainee_id, "salary": salary,
            "salary_period": "Monthly", "effective_date": when.isoformat(),
            "source": "Trainee", "verification_status": "Unverified",
        })
        api.post("/api/employment-status", json={
            "employment_id": employment_id, "trainee_id": trainee_id,
            "employment_status": "Active", "status_date": when.isoformat(),
        })
        stats["employments"] += 1
    elif outcome_type == "Self-employed":
        api.post("/api/self-employment", json={
            "outcome_id": outcome_id, "trainee_id": trainee_id,
            "business_name": f"{trainee_id[-3:]} {business.split()[0]} Services", "business_type": business,
            "start_date": when.isoformat(), "monthly_income": round(course[7] * RNG.uniform(0.7, 1.5), -2),
            "number_of_workers": RNG.choice([0, 0, 1, 2]),
        })
    elif outcome_type == "Apprenticeship":
        api.post("/api/apprenticeships", json={
            "outcome_id": outcome_id, "trainee_id": trainee_id, "organization_name": employer,
            "role": apprentice_role, "start_date": when.isoformat(),
            "end_date": (when + timedelta(days=365)).isoformat(),
            "monthly_stipend": RNG.choice([7000, 8000, 9000, 10000]),
        })
    elif outcome_type == "Unemployed":
        api.post("/api/non-placement", json={
            "outcome_id": outcome_id, "trainee_id": trainee_id,
            "reason_category": RNG.choice(NON_PLACEMENT_REASONS),
        })
    stats[outcome_type] = stats.get(outcome_type, 0) + 1
    return outcome_id, employment_id


def verify_employment(api, trainee_id, employment_id, when, stats):
    roll = RNG.random()
    if roll < 0.5:  # employer confirmation link, as an employer would use it
        link = api.post(f"/api/employment/{employment_id}/verification-request",
                        json={"employer_contact": "hr@employer.example"})["link"]
        token = link.rsplit("/", 1)[1]
        confirmed = RNG.random() < 0.92
        latest = api.get(f"/api/employment/{employment_id}/wage-history")["wage_history"][-1]
        body = {"employment_confirmed": confirmed, "verified_by": "HR Manager"}
        if confirmed:  # employer confirms the latest wage on record
            body.update({"salary": latest["salary"], "salary_period": latest["salary_period"]})
        api.post(f"/api/employer-verify/{token}", json=body)
        stats["employer_link_verifications"] += 1
    elif roll < 0.75:
        api.post("/api/employer-verifications", json={
            "employment_id": employment_id, "trainee_id": trainee_id,
            "employer_name": api.get(f"/api/employment/{employment_id}")["company_name"],
            "verification_status": "Verified",
            "verification_method": RNG.choice(["Document", "Employer Contact"]),
            "verified_date": when.isoformat(), "verified_by": "District Placement Officer",
        })
    # else: stays unverified -> shows up in data-quality


def later_wages_and_status(api, trainee_id, employment_id, fus, course, stats):
    wages = api.get(f"/api/employment/{employment_id}/wage-history")["wage_history"]
    monthly = wages[-1]["salary"]
    for fu in fus:
        when = date.fromisoformat(fu["scheduled_date"])
        if fu["followup_type"] not in ("6_MONTH", "12_MONTH") or when > TODAY:
            continue
        monthly = round(monthly * RNG.uniform(1.04, 1.18), -2)
        annual = RNG.random() < 0.35  # some employers quote annual CTC
        api.post("/api/wage-history", json={
            "employment_id": employment_id, "trainee_id": trainee_id,
            "salary": monthly * 12 if annual else monthly, "salary_period": "Annual" if annual else "Monthly",
            "effective_date": when.isoformat(), "source": RNG.choice(["Employer", "Trainee"]),
            "verification_status": RNG.choice(["Verified", "Unverified"]),
        })
    if RNG.random() < course[6]:
        left_on = min(TODAY, date.fromisoformat(wages[0]["effective_date"]) + timedelta(days=RNG.randint(60, 300)))
        api.post("/api/employment-status", json={
            "employment_id": employment_id, "trainee_id": trainee_id,
            "employment_status": RNG.choice(["Left Job", "Left Job", "Left Job", "Terminated"]),
            "status_date": left_on.isoformat(), "reason": RNG.choice(ATTRITION_REASONS),
        })
        stats["attrition"] += 1


def run_followups(api, trainee_id, training_id, end, course, stats):
    api.post(f"/api/followups/generate/{training_id}")
    fus = api.get(f"/api/trainees/{trainee_id}/followup-timeline")["followups"]
    fus = [f for f in fus if f["training_id"] == training_id]
    due = [f for f in fus if date.fromisoformat(f["scheduled_date"]) <= TODAY]
    if not due:
        return

    final = pick_weighted(course[3])
    # Some trainees are unemployed at 30 days and find work by 90 days
    early_then_job = final == "Employed" and len(due) >= 2 and RNG.random() < 0.3
    leave_last_for_dispatch = RNG.random() < 0.25
    # Recent graduates answer their first check-in through the self-report link
    recent = date.fromisoformat(due[0]["scheduled_date"]) >= TODAY - timedelta(days=60)
    use_self_report = recent and final != "Not Reachable" and RNG.random() < 0.8

    outcome_recorded = False
    employment_id = None
    for index, fu in enumerate(due):
        is_last = index == len(due) - 1
        when = min(TODAY, date.fromisoformat(fu["scheduled_date"]) + timedelta(days=RNG.randint(0, 6)))

        if final == "Not Reachable":
            for status in RNG.sample(["No Response", "Busy", "Invalid Contact", "Not Reachable"], 2):
                attempt(api, fu["followup_id"], when, status, RNG.choice(["Phone", "SMS"]))
            if not outcome_recorded:
                oid, _ = record_outcome(api, trainee_id, training_id, "Not Reachable", when, course, stats)
                outcome_recorded = True
            api.post(f"/api/followups/{fu['followup_id']}/not-reachable",
                     json={"notes": "Number switched off on repeated attempts"})
            continue

        if is_last and leave_last_for_dispatch:
            stats["left_due_for_dispatch"] += 1
            continue  # stays Scheduled -> appears in pending / overdue / dispatch

        if index == 0 and use_self_report:
            token = create_link_token(PURPOSE_SELF_REPORT, fu["followup_id"])
            report = {"outcome_type": final,
                      "training_relevance": max(1, min(5, round(RNG.gauss(course[4], 0.9)))),
                      "skill_gap": RNG.random() < course[5],
                      "additional_training_needed": RNG.random() < course[5]}
            if final in ("Employed", "Self-employed", "Apprenticeship"):
                roles = ROLES[course[0]]
                report.update({
                    "organisation_name": RNG.choice(EMPLOYERS[course[0]]),
                    "role": {"Employed": roles[0], "Self-employed": roles[1], "Apprenticeship": roles[2]}[final],
                    "monthly_income": round(course[7] * RNG.uniform(0.85, 1.2), -2),
                    "start_date": when.isoformat(),
                })
            if final == "Unemployed":
                report["unemployment_reason"] = RNG.choice(NON_PLACEMENT_REASONS)
            api.post(f"/api/self-report/{token}", json=report)
            stats["self_reports"] += 1
            return

        if RNG.random() < 0.12 and not is_last:  # a missed check-in in the middle
            attempt(api, fu["followup_id"], when, "No Response")
            api.post(f"/api/followups/{fu['followup_id']}/missed", json={"notes": "No response after 3 calls"})
            continue

        if RNG.random() < 0.4:
            attempt(api, fu["followup_id"], when - timedelta(days=1), RNG.choice(["No Response", "Busy"]))
        attempt(api, fu["followup_id"], when, "Successful",
                RNG.choice(["Phone", "Phone", "WhatsApp", "In Person"]))

        current = "Unemployed" if early_then_job and index == 0 else final
        followup_update(api, fu, current, course,
                        reason=RNG.choice(NON_PLACEMENT_REASONS) if current == "Unemployed" else None)
        complete = {"completed_date": when.isoformat()}
        if not outcome_recorded or (early_then_job and index == 1):
            oid, emp = record_outcome(api, trainee_id, training_id, current, when, course, stats)
            complete["outcome_id"] = oid
            outcome_recorded = current == final
            if emp:
                employment_id, employed_on = emp, when
        api.post(f"/api/followups/{fu['followup_id']}/complete", json=complete)

    if employment_id:
        later_wages_and_status(api, trainee_id, employment_id, fus, course, stats)
        verify_employment(api, trainee_id, employment_id, employed_on, stats)


def main():
    init_db()  # creates any missing tables/columns (non-destructive)
    api = Api()
    existing = api.client.get("/api/identity/lookup", params={"id_type": MARKER_TYPE, "id_value": f"{MARKER_PREFIX}0001"})
    if existing.status_code == 200:
        print("Demo data already present (found", existing.json()["trainee_id"], ") - nothing to do.")
        return

    stats = {"trainees": 0, "employments": 0, "self_reports": 0, "attrition": 0,
             "employer_link_verifications": 0, "left_due_for_dispatch": 0}
    created = []
    for n in range(1, 49):
        district = DISTRICTS[(n - 1) % len(DISTRICTS)]
        course = COURSES[RNG.randrange(len(COURSES))]
        trainee_id, payload = register(api, n, district, course)
        created.append((trainee_id, payload))
        stats["trainees"] += 1

        roll = RNG.random()
        if roll < 0.06:
            add_training(api, trainee_id, course, "Ongoing", None)
        elif roll < 0.12:
            add_training(api, trainee_id, course, "Dropped", None)
        else:
            end = TODAY - timedelta(days=RNG.randint(20, 560))
            training_id = add_training(api, trainee_id, course, "Completed", end)
            run_followups(api, trainee_id, training_id, end, course, stats)
        print(f"  {trainee_id}  {course[0]:<32} {district[0]}  ({api.calls} API calls so far)")

    # One person registered twice (new phone, no ID given) -> flagged as possible duplicate
    dup_id, dup_payload = created[5]
    again = dict(dup_payload, phone=new_phone(), external_ids=[])
    again.pop("email", None)
    res = api.post("/api/trainees", json=again)
    print(f"  {res['trainee_id']}  duplicate registration of {dup_id} -> flagged {res['possible_duplicates']}")

    # Two trainees withdraw consent (their records stay, analytics exclude them)
    for trainee_id, _ in created[10:12]:
        api.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": False})

    print("\nDone.", stats, f"{api.calls} API calls.")
    print("Demo districts:", ", ".join(d[0] for d in DISTRICTS))


if __name__ == "__main__":
    main()
