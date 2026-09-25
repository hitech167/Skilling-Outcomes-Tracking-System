# SIH26135 — Backend Technical Documentation

**Longitudinal Skilling Outcomes and Impact Measurement System**

This document describes the complete backend: what it does, how it is built,
every table and endpoint, how each metric is calculated, how privacy and
consent are enforced, and how to run, test and demo it.

---

## Contents

1. [Purpose](#1-purpose)
2. [Technology](#2-technology)
3. [Project structure](#3-project-structure)
4. [Architecture and data flow](#4-architecture-and-data-flow)
5. [Identifiers](#5-identifiers)
6. [Database schema](#6-database-schema)
7. [Access control](#7-access-control)
8. [Privacy and consent](#8-privacy-and-consent)
9. [API reference](#9-api-reference)
10. [Follow-up system](#10-follow-up-system)
11. [Self-report and employer confirmation links](#11-self-report-and-employer-confirmation-links)
12. [Cross-programme identity](#12-cross-programme-identity)
13. [Analytics — metric definitions](#13-analytics--metric-definitions)
14. [Insights — rule-based intelligence](#14-insights--rule-based-intelligence)
15. [Data quality](#15-data-quality)
16. [Reliability rules](#16-reliability-rules)
17. [Configuration](#17-configuration)
18. [Running the backend](#18-running-the-backend)
19. [Testing](#19-testing)
20. [Demo data and demo walkthrough](#20-demo-data-and-demo-walkthrough)
21. [Problem-statement coverage](#21-problem-statement-coverage)
22. [Known limits](#22-known-limits)

---

## 1. Purpose

Training systems usually record enrolment, attendance, assessment and
certification, but lose track of trainees afterwards. SIH26135 asks for a
system that follows trainees **after** training — employment,
self-employment, apprenticeship, job retention, wage progression, training
relevance — in a way that is credible, low-burden and privacy-conscious,
even when trainees change phone numbers or locations, employers report
inconsistently, and programmes use different identifiers.

This backend provides:

- a **stable identity** per trainee, linked across programmes
- **consent-based** records with withdrawal
- training, assessment and certification records
- **automated and assisted follow-ups** at 30 days, 90 days, 6 months and 12 months
- outcome capture for all six outcome types
- **employer validation**, wage history and employment-status history
- **analytics** (placement, employment, retention, wages, course / provider /
  district / demographic / cohort breakdowns, attrition, skill gaps,
  training relevance)
- **rule-based insights** for programme improvement, remedial action,
  resource allocation, accountability and data quality

---

## 2. Technology

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI 0.115 (Swagger UI at `/docs`) |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic 2.10 |
| Database | PostgreSQL (Supabase) via psycopg2 |
| Auth | JWT (PyJWT, HS256) with OAuth2 password flow |
| Email | Python `smtplib` (e.g. Gmail SMTP) |
| SMS | Generic HTTP webhook to any SMS gateway |
| Tests | pytest + FastAPI TestClient on in-memory SQLite |

No Celery, Redis, message broker or ML libraries are required.

---

## 3. Project structure

```
backend/
├── main.py                      FastAPI app, lifespan, router registration, access control
├── requirements.txt
├── .env.example                 Placeholder configuration (real .env is git-ignored)
├── database/
│   ├── connection.py            Engine, session, init_db() (tables, sequences, additive columns)
│   └── models.py                All SQLAlchemy models (16 tables)
├── schemas/                     Pydantic request/response models, one file per area
├── routes/                      API routers, one file per area
│   ├── _shared.py               "get X or 404" helpers
│   ├── auth.py                  Login / current user
│   ├── trainees.py              Registration, profile, contact, consent
│   ├── training_records.py      Training, assessment, certification
│   ├── outcomes.py, employment.py, self_employment.py,
│   │   apprenticeship.py, non_placement.py
│   ├── followup.py              Phase 3 follow-up CRUD
│   ├── followup_tracking.py     Schedule generation, attempts, updates, summaries
│   ├── employer_verifications.py, wage_history.py, employment_status.py
│   ├── self_service.py          Public link forms + dispatch + outbox
│   ├── identity.py              External IDs, lookup, duplicates
│   ├── analytics.py             /api/analytics/*
│   └── insights.py              /api/insights/*
├── services/
│   ├── auth.py                  JWT, roles, single-purpose link tokens
│   ├── consent_scope.py         Excludes withdrawn trainees from analytics
│   ├── followup_scheduler.py    30/90-day, 6/12-month date arithmetic
│   ├── notification_service.py  Dispatcher, email/SMS delivery, outbox
│   ├── self_service.py          Self-report + employer confirmation processing
│   ├── identity_service.py      External-ID linking, duplicate detection
│   ├── analytics_service.py     Phase 6 metrics
│   └── insights_service.py      Phase 7 insights, data quality
├── scripts/
│   └── seed_demo_data.py        Inserts a realistic 48-trainee demo dataset
├── tests/                       127 tests (see §19)
└── docs/
    └── BACKEND.md               This document
```

---

## 4. Architecture and data flow

```
TRAINEE (consent, stable TRN id, external programme IDs)
   │
   ▼
TRAINING (programme, course, provider, attendance, assessment, certification)
   │  status = Completed
   ▼
FOLLOW-UP SCHEDULE  30_DAY · 90_DAY · 6_MONTH · 12_MONTH
   │
   ├── automated: dispatcher → Email / SMS / phone queue → self-report link
   └── assisted:  staff call → attempts → outcome update → complete
   ▼
OUTCOME  Employed · Self-employed · Apprenticeship · Unemployed ·
         Further Education · Not Reachable
   │
   ├── Employed ──► EMPLOYMENT ──► employer verification (link / document / contact)
   │                     ├──► wage history (Monthly / Annual, source, verified?)
   │                     └──► status history (Active → Left Job / Terminated ...)
   ├── Self-employed ──► business record
   ├── Apprenticeship ──► apprenticeship record
   └── Unemployed ──► non-placement reason
   ▼
ANALYTICS (consented trainees only) ──► INSIGHTS ──► programme improvement,
remedial actions, resource allocation, accountability, data quality
```

**Layering:** routes validate input and handle HTTP concerns; services hold
business logic and all calculations; models describe tables. Analytics and
insights are read-only and never write to the database.

---

## 5. Identifiers

Every record has an internal integer primary key (never exposed) and a
permanent public ID generated from a PostgreSQL sequence, so two requests
can never receive the same ID.

| Record | Format | Sequence |
|---|---|---|
| Trainee | `TRN000001` | `trainee_id_seq` |
| Training record | `TRC000001` | `training_record_id_seq` |
| Outcome | `OUT000001` | `outcome_id_seq` |
| Employment | `EMP000001` | `employment_id_seq` |
| Self-employment | `SEM000001` | `self_employment_id_seq` |
| Apprenticeship | `APR000001` | `apprenticeship_id_seq` |
| Non-placement | `NPL000001` | `non_placement_id_seq` |
| Follow-up | `FUP000001` | `followup_id_seq` |
| Contact attempt | `ATT000001` | `followup_attempt_id_seq` |
| Follow-up outcome update | `FOU000001` | `followup_outcome_update_id_seq` |
| Employer verification | `VER000001` | `employer_verification_id_seq` |
| Wage record | `WAGE000001` | `wage_history_id_seq` |
| Status record | `EST000001` | `employment_status_id_seq` |
| Notification | `NTF000001` | `notification_id_seq` |

The phone number is **not** the identity: trainees change numbers, so the
`TRN` ID stays fixed while contact details are updated.

---

## 6. Database schema

16 tables. All foreign keys use `ON DELETE CASCADE` (except
`followups.outcome_pk_id`, which is `SET NULL`). Rows are never deleted by the
application: history tables only ever grow.

### 6.1 `trainees`
| Column | Notes |
|---|---|
| `trainee_id` | Public stable ID (unique) |
| `full_name`, `dob`, `gender`, `district`, `current_location` | Profile |
| `phone` (unique), `email` (unique, optional), `preferred_contact` | `SMS` / `Email` / `Phone` |
| `consent_given`, `consent_date` | Current consent state and when it was set |

### 6.2 `training_records`
`record_id`, `trainee_pk_id`, `program_name`, `course_name`, `provider_name`,
`start_date`, `end_date`, `status` (`Enrolled` / `Ongoing` / `Completed` /
`Dropped`), `attendance_percentage` (0–100), `assessment_score` (0–100),
`assessment_status` (`Pending` / `Passed` / `Failed`), `certification_issued`,
`certification_id`.

Rules: `end_date` ≥ `start_date`; a certificate can only be issued when the
status is `Completed`.

### 6.3 Outcome tables
| Table | Created for outcome type | Key fields |
|---|---|---|
| `outcomes` | all | `outcome_type`, `status_date`, `notes`, links to trainee + training |
| `employment_records` | Employed | company, role, joining date, salary, status, location, relevance |
| `self_employment_records` | Self-employed | business name/type, start date, monthly income, workers |
| `apprenticeship_records` | Apprenticeship | organisation, role, dates, monthly stipend |
| `non_placement_records` | Unemployed | `reason_category`, details |

Detail records are only accepted against an outcome of the matching type
and the same trainee. A training can have several outcomes over time
(longitudinal); analytics use the latest one (§13).

Non-placement categories: Skill Gap, Lack of Jobs, Low Salary, Location
Problem, Relocation Issue, Personal/Family Reason, Further Education, Other.

### 6.4 Employment history tables
| Table | Purpose | Values |
|---|---|---|
| `employer_verifications` | One row per verification attempt (history kept; latest = current) | status: Pending / Verified / Rejected / Unable to Verify; method: Employer Portal / Employer Contact / Document / Trainee Confirmation / Admin Verification |
| `wage_history` | One row per known salary point; the original salary is never overwritten | `salary`, `salary_period` (Monthly / Annual), `effective_date`, `source` (Trainee / Employer / Document / Admin), `verification_status` (Unverified / Verified) |
| `employment_status_history` | Retention timeline | Active / Left Job / Terminated / On Leave / Unknown, with date and reason |

### 6.5 Follow-up tables
| Table | Purpose |
|---|---|
| `followups` | `followup_type` (30_DAY / 90_DAY / 6_MONTH / 12_MONTH), `scheduled_date`, `completed_date`, `status` (Scheduled / Completed / Missed / Not Reachable), linked outcome |
| `followup_attempts` | Every contact attempt: date, method (Phone / SMS / WhatsApp / Email / In Person / Other), result (Successful / No Response / Busy / Invalid Contact / Not Reachable / Other) |
| `followup_outcome_updates` | Situation captured at a follow-up: current status, training relevance (1–5), skill gap, additional training needed, unemployment reason |

### 6.6 Phase 8 tables
| Table | Purpose |
|---|---|
| `trainee_external_ids` | IDs from other programmes (`id_type`, `id_value`, `source_programme`); unique on (`id_type`, `id_value`) |
| `trainee_consent_history` | One row per consent grant / withdrawal: `consent_given`, `source` (`registration` / `admin` / `self`), `method` (Paper form / Digital form / Verbal / Self-service), `recorded_by`, `notes`, `changed_at` |
| `trainee_contact_history` | One row per changed contact field: `field`, `old_value`, `new_value`, `source` (`self` / `admin`), `changed_at` |
| `notifications` | Outbox of automated messages: purpose, channel, recipient, message, status (Queued / Sent / Failed), provider, error, timestamps |

### 6.7 Schema changes are non-destructive
`init_db()` runs on every startup and only uses `CREATE TABLE/SEQUENCE/INDEX
IF NOT EXISTS` and `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Existing rows
keep their data; new columns (`program_name`, `assessment_status`) are
simply empty on older rows.

---

## 7. Access control

Login: `POST /api/auth/token` with form fields `username` and `password`
returns a bearer JWT (HS256, default 60 minutes). In Swagger use the
**Authorize** button. Users are configured in `.env` — there is no user table.

| Role | Access |
|---|---|
| `admin` | All record-level endpoints (trainees, contact details, training, outcomes, follow-ups, employment, verification, wages, status history, identity, outbox) **and** analytics/insights |
| `analyst` | `/api/analytics/*` and `/api/insights/*` only |
| Public | `/`, `/api/system/health`, `/docs`, `/openapi.json`, `/api/auth/token`, and the signed self-report / employer-confirmation links |

Protection is applied per router in `main.py`, so a new endpoint added to an
existing router is protected automatically. A test calls every non-public
route without a token and expects `401`.

Security properties:

- **Fails closed:** if `JWT_SECRET_KEY` is missing or shorter than 32
  characters, no token can be issued or accepted (`503`).
- Tokens are checked against the currently configured users, so changing
  a password or removing a user in `.env` revokes that user's access
  after restart.
- Password comparison is constant-time; failed logins never log the password.
- Link tokens (§11) carry a `purpose` and no `role`, so they can never be
  used to call the API, and login tokens can never be used as links.

---

## 8. Privacy and consent

- **Consent is required at registration.** `consent_given` must be `true`.
  If `consent_analytics` or `consent_privacy_notice` is sent as `false`,
  registration is refused rather than silently ignored.
- **Withdrawal:** `POST /api/trainees/{id}/consent` with
  `{"consent_given": false}`. From then on:
  - no new follow-up schedules, contact attempts, automated messages or
    self-reports (`409`)
  - the trainee is **excluded from every analytics and insights figure**
    (`services/consent_scope.py` adds the filter to every analytics query)
  - nothing is deleted; admins still see the records, and re-granting
    consent restores the trainee to the statistics
- **Minimal exposure:**
  - `GET /api/trainees/{id}` never returns phone, email or date of birth
  - contact details are only at `GET /api/trainees/{id}/contact` (admin)
  - analytics and insights return counts, rates and averages only — no
    names, phone numbers, emails, DOBs, trainee IDs or employer contacts
    (checked by an automated test)
  - the self-report form shows only first name, course and provider
- **Aadhaar numbers are never stored:** an external ID of type "Aadhaar",
  or any 12-digit value, is rejected.
- **Logs** record IDs only, never personal data.
- **Secrets** live only in `.env`, which is git-ignored.

---

## 9. API reference

All paths are under the same host (default `http://127.0.0.1:8000`).
Access: **A** = admin, **A/An** = admin or analyst, **P** = public.

### 9.1 Authentication (P)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/token` | Log in, get a bearer token |
| GET | `/api/auth/me` | Current user and role (any valid token) |

### 9.2 Trainees (A)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/trainees` | Register (consent required; optional `external_ids`; returns `possible_duplicates`) |
| GET | `/api/trainees/{trainee_id}` | Profile without phone/email/DOB |
| GET | `/api/trainees/{trainee_id}/contact` | Contact details for assisted follow-ups |
| PATCH | `/api/trainees/{trainee_id}` | Update phone / email / district / location / preferred contact (logged to contact history) |
| GET | `/api/trainees/{trainee_id}/consent-history` | Consent audit trail, newest first |
| GET | `/api/trainees/{trainee_id}/contact-history` | Previous contact values, newest first |
| POST | `/api/trainees/{trainee_id}/consent` | Withdraw (`false`) or re-grant (`true`) consent |

### 9.3 Training records (A)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/trainees/{trainee_id}/training-records` | Add a training record |
| GET | `/api/trainees/{trainee_id}/training-records` | List a trainee's training |
| GET | `/api/training-records/{record_id}` | One record |
| PATCH | `/api/training-records/{record_id}` | Update (e.g. mark Completed, add assessment) |
| POST | `/api/training` · `/api/trainees/{id}/training` | Aliases for create |
| GET | `/api/training/{record_id}` · `/api/trainees/{id}/training` | Aliases for read |

### 9.4 Outcomes and details (A)
| Method | Path | Purpose |
|---|---|---|
| POST / GET | `/api/outcomes` · `/api/outcomes/{outcome_id}` | Record / read an outcome |
| GET | `/api/trainees/{trainee_id}/outcomes` | A trainee's outcomes over time |
| POST / GET | `/api/employment` · `/api/employment/{id}` | Job details (Employed) |
| POST / GET | `/api/self-employment` · `/api/self-employment/{id}` | Business details |
| POST / GET | `/api/apprenticeships` · `/api/apprenticeships/{id}` | Apprenticeship details |
| POST / GET | `/api/non-placement` · `/api/non-placement/{id}` | Non-placement reason (Unemployed) |

### 9.5 Employer verification, wages, retention (A)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/employer-verifications` | Record a verification (document, call, …) |
| GET | `/api/employer-verifications/{verification_id}` | One verification |
| POST | `/api/employment-signals/import` | Import external placements from CSV (§11.4) |
| GET | `/api/employment/{employment_id}/verification` | Latest verification for a job |
| POST | `/api/employment/{employment_id}/verification-request` | Create an employer confirmation link (§11) |
| POST | `/api/wage-history` | Add a salary point |
| GET | `/api/employment/{employment_id}/wage-history` | Salary history, oldest first |
| POST | `/api/employment-status` | Record a status change |
| GET | `/api/employment/{employment_id}/status-history` | Status timeline |
| GET | `/api/employment/{employment_id}/summary` | Verification + salary (raw and monthly-normalised, growth %) + current status |
| GET | `/api/trainees/{trainee_id}/employment-history` | All jobs of a trainee |

### 9.6 Follow-ups (A)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/followups/generate/{training_id}` | Create the 4-check-in schedule (idempotent) |
| POST | `/api/followups` | Schedule one follow-up manually (one per type per training) |
| GET | `/api/followups/{followup_id}` | One follow-up |
| PATCH | `/api/followups/{followup_id}` | Update status / completion / linked outcome |
| GET | `/api/followups/pending` · `/upcoming?days=7` · `/overdue` · `/summary` | Work queues and counts |
| POST | `/api/followups/{id}/complete` · `/missed` · `/not-reachable` | Close a follow-up |
| POST / GET | `/api/followups/{id}/attempt` · `/attempts` | Contact attempts |
| POST | `/api/followups/{id}/outcome-update` | Capture current situation, relevance, skill gap |
| GET | `/api/followups/{id}/summary` | Attempts, latest attempt, current outcome |
| GET | `/api/trainees/{trainee_id}/followups` · `/followup-timeline` | A trainee's follow-ups |
| POST | `/api/followups/dispatch-due` | Send due check-ins automatically (§10) |
| POST | `/api/verifications/remind-pending` | Remind silent employers; mark unresponsive after 3 requests (§11.2) |
| GET | `/api/followups/{followup_id}/self-report-link` | Link to share manually (e.g. WhatsApp) |
| GET | `/api/notifications?status=Queued` | Outbox |
| POST | `/api/notifications/{notification_id}/mark-sent` | Staff sent / called manually |

### 9.7 Identity (A)
| Method | Path | Purpose |
|---|---|---|
| POST / GET | `/api/trainees/{trainee_id}/external-ids` | Link / list other-programme IDs |
| GET | `/api/identity/lookup?id_type=…&id_value=…` | Find the trainee for an external ID |
| GET | `/api/identity/possible-duplicates` | Same name + DOB registered more than once |

### 9.8 Public links (P, token required in path)
| Method | Path | Purpose |
|---|---|---|
| GET | `/self-report/{token}` | Trainee mobile form (HTML) |
| GET / POST | `/api/self-report/{token}` | Form context / submit |
| POST | `/api/self-report/{token}/consent` | Trainee withdraws / re-grants own consent (logged, source `self`) |
| GET / PATCH | `/api/self-report/{token}/contact` | Trainee views / updates own phone, email, district, location, preferred contact (409 if number taken, 403 if consent withdrawn) |
| GET | `/employer-verify/{token}` | Employer form (HTML) |
| GET / POST | `/api/employer-verify/{token}` | Form context / submit |

### 9.9 Analytics (A/An) — see §13
`overview` (optional `?district=`), `placement-rate`, `employment-rate`,
`retention-rate`, `wage-progression`, `course-performance`,
`provider-performance`, `district-outcomes`, `demographics`,
`non-placement-reasons`, `attrition`, `skill-gaps`, `training-relevance`,
`cohort`, `accountability`, `remedial-insights`, `resource-allocation` — all
`GET /api/analytics/<name>`.

### 9.10 Insights (A/An) — see §14
`skill-gaps`, `skill-gaps/by-course`, `non-placement`, `attrition`,
`training-relevance`, `additional-training`, `additional-training/by-course`,
`longitudinal-outcomes`, `programme-improvement`, `remedial-actions`,
`resource-allocation`, `accountability`, `data-quality`, `summary` — all
`GET /api/insights/<name>`.

### 9.11 Health (P)
`GET /` and `GET /api/system/health` (reports database connectivity).

### 9.12 Status codes
| Code | Meaning |
|---|---|
| 200 / 201 | OK / created |
| 400 | Rule violated (e.g. training not Completed, record belongs to another trainee, detail type doesn't match outcome) |
| 401 | Missing, invalid or expired token |
| 403 | Role not allowed |
| 404 | Record or link not found / link invalid or expired |
| 409 | Conflict: duplicate phone/email/external ID, duplicate follow-up type, consent withdrawn, link already used |
| 422 | Validation failed |
| 503 | Database unavailable, or auth not configured |

---

## 10. Follow-up system

### 10.1 Schedule
`POST /api/followups/generate/{training_id}` (training must be `Completed`
with an `end_date`, and the trainee must have consent) creates:

| Type | Date |
|---|---|
| `30_DAY` | end date + 30 days |
| `90_DAY` | end date + 90 days |
| `6_MONTH` | end date + 6 calendar months |
| `12_MONTH` | end date + 12 calendar months |

Month arithmetic is calendar-correct (31 Jan + 1 month = 28/29 Feb).
Repeating the call creates nothing new, and the training row is locked
during generation so two simultaneous calls cannot create duplicates.

### 10.2 Automated dispatch
`POST /api/followups/dispatch-due`, or automatically every
`FOLLOWUP_AUTO_DISPATCH_HOURS`:

1. Finds follow-ups that are **Scheduled** and due (`scheduled_date ≤ today`).
2. Keeps only the **most recent due check-in per training** — a trainee
   with a backlog gets one message, not four (`skipped_superseded`).
3. Skips trainees without consent (`skipped_no_consent`) and anyone
   messaged about that check-in in the last 7 days
   (`skipped_recently_contacted`).
4. Creates a personal self-report link (valid 30 days) and sends it on the
   trainee's preferred channel:

| Preferred contact | Delivery |
|---|---|
| Email | SMTP (e.g. Gmail) when `SMTP_HOST` is set |
| SMS | HTTP gateway at `SMS_WEBHOOK_URL` when set |
| Phone | Always queued for a staff call |

Every message is stored in `notifications` as **Sent**, **Queued** (no
provider yet / phone call needed) or **Failed** (with the provider error),
so nothing is silently dropped. Staff work the queue via
`GET /api/notifications?status=Queued` and `POST …/mark-sent`.

### 10.3 Assisted follow-up
Staff can do everything manually: log attempts (including failed ones),
record an outcome update, complete / mark missed / mark not reachable,
and view the per-follow-up summary and the trainee timeline.

---

## 11. Self-report and employer confirmation links

### 11.1 Trainee self-report
The link opens a small mobile form (`/self-report/{token}`) — no login, no
app. The trainee chooses what they are doing now (job / own business /
apprenticeship / looking for work / studying) and optionally gives
employer, role, start date, monthly income, training relevance (1–5), skill
gap and whether they want more training.

One submission records, in a single transaction:

- a follow-up outcome update (relevance, skill gap, training need)
- an outcome of the reported type
- the matching detail: job (with a **Trainee / Unverified** wage and a
  **Pending** employer verification), business, apprenticeship, or
  non-placement reason
- a successful contact attempt
- the follow-up marked **Completed** and linked to the outcome

If the trainee reports the **same employer / business / apprenticeship**
they already have, the existing record is extended (a new wage point only
if the income changed; status back to Active if needed) instead of a
duplicate being created.

### 11.1b Consent evidence and self-service withdrawal
Registration accepts optional `consent_method` and `consent_recorded_by`, so
consent captured by staff (e.g. a signed paper form) is evidenced. Every
grant or withdrawal - at registration, by staff (`POST .../consent`, with
optional `method`, `recorded_by`, `notes`) or by the trainee
(`POST /api/self-report/{token}/consent`) - is appended to
`trainee_consent_history`; `trainees.consent_given` remains the flag the rest
of the app checks. A trainee who has withdrawn can still re-grant from the
same link.

### 11.1a Trainee contact changes
`GET / PATCH /api/self-report/{token}/contact` lets a trainee change their
own phone, email, district, location and preferred contact using the same
signed link, so a new number or move does not need staff. Changes are
validated like registration, logged to `trainee_contact_history` with
`source = self`, and refused once consent is withdrawn. The context
endpoint never returns the phone number or email.

### 11.2 Employer confirmation
`POST /api/employment/{id}/verification-request` creates a Pending
verification (method *Employer Portal*) and a link, emailed automatically if
the contact is an email address and SMTP is configured. The employer's form
(`/employer-verify/{token}`) shows the employee name, role, company and
joining date, and asks whether the employment is confirmed, the current
status, salary and period, and the verifier's name. Submitting marks the
verification **Verified** or **Rejected**, and adds an **Employer /
Verified** wage and a status record when given.

**Reminders.** `POST /api/verifications/remind-pending` looks at every
Pending verification that has an employer contact. If the last request is
older than 7 days it sends a reminder with a fresh link; once 3 requests
have gone unanswered it sets the verification to **Unable to Verify** with
the note "Employer unresponsive". It runs only when called (schedule it).

### 11.4 External employment signals
`POST /api/employment-signals/import` takes a CSV (max 2 MB / 5000 rows), a
`source` label (e.g. EPFO) and optional `dry_run=true`. Each row identifies the
trainee by `trainee_id`, `phone` or `external_id` (`TYPE:VALUE`) and gives
`employer_name`, `start_date`, and optionally `job_role`, `monthly_salary`,
`reference`. For a matched trainee with consent and a training record it adds,
on their latest training, an **Employed** outcome, an employment record, a
**Document / Verified** wage and an employer verification **Verified** by
*Document* (verifier = source). If the trainee already has that employer, no
duplicate is made and any Pending verification is resolved instead. The
response counts `created`, `verified_existing`, `already_recorded`,
`trainee_not_found`, `no_consent`, `no_training`, `invalid` and lists up to 50
problem rows.

### 11.3 Link security
- Signed with the server secret; include a purpose; expire after 30 days
- **Single use:** the row is locked and re-read before accepting, so
  simultaneous submissions (e.g. double-clicks) are accepted exactly once
  (`409` for the rest); the form also disables its button while sending
- Invalid, expired or wrong-purpose links return `404`
- Pages are sent with `no-store`, `noindex` and `no-referrer`

---

## 12. Cross-programme identity

- Link IDs from other programmes (Skill India Digital ID, PMKVY /
  DDU-GKY candidate IDs, state scheme numbers) to the one stable
  `trainee_id`, at registration (`external_ids`) or later.
- `GET /api/identity/lookup` finds the trainee for any linked ID (type is
  case-insensitive, value is normalised to upper case).
- **Duplicate prevention:** registering with, or linking, an ID that already
  belongs to another trainee is refused with `409` naming the existing
  trainee.
- **Duplicate detection:** same normalised name + same date of birth is
  returned as `possible_duplicates` at registration and listed at
  `/api/identity/possible-duplicates`. Records are flagged, never merged
  automatically.

---

## 13. Analytics — metric definitions

All analytics are read-only, computed on request, and include only trainees
with active consent.

| Metric | Definition |
|---|---|
| Eligible population | Completed training records |
| **Placement rate** | (Employed + Self-employed + Apprenticeship) ÷ completed trainings × 100 |
| **Employment rate** | Employed ÷ completed trainings × 100 |
| Outcome used | The **latest** outcome per training (by `status_date`, then id), so a training counts once and later updates replace earlier states |
| Not placement | Unemployed, Further Education, Not Reachable, or no outcome yet |
| **Retention rate** | Employment records whose latest status is `Active` ÷ all employment records. Latest status = newest status-history row, falling back to the status on the employment record |
| **Attrition rate** | Employment records whose latest status is `Left Job`, `Left` or `Terminated` ÷ all employment records; reasons come from status history ("Not Specified" when missing) |
| **Wage progression** | Per employment: first vs latest wage by `effective_date`. Every salary is converted to a **monthly equivalent** (Annual ÷ 12) for the calculation only; stored values and periods are never changed. Growth needs ≥ 2 wage records; growth from 0 is undefined |
| Course / provider / district performance | The placement breakdown grouped by course, provider or trainee district |
| **Demographics** | By gender and age group (Under 18, 18–24, 25–34, 35–44, 45+), counting distinct trainees; placement rate = placed ÷ trainees with ≥ 1 completed training |
| **Cohort** | Grouped by training completion month (`YYYY-MM`) |
| Non-placement reasons | Count and share of each reason category |
| Skill gaps | Share of follow-up updates reporting a skill gap / additional training need |
| Training relevance | Average and distribution of 1–5 ratings |
| Accountability | Completion, placement, employment, retention, relevance, skill gap, attrition and wage growth — factual indicators with definitions, no rankings |
| Resource allocation | Per district: trainees, unemployed, skill gaps, non-placement, attrition, additional training needed |

**Missing data stays missing:** averages with no data are `null`
(never 0), lists are `[]`, and a rate over an empty population is `0` shown
next to its population count.

---

## 14. Insights — rule-based intelligence

No AI/ML. Every statement is generated from stored data by a fixed,
explainable rule, and states the figure that triggered it.

| Area | Rule (trigger) |
|---|---|
| Skill gap | ≥ 25% of follow-up updates report a skill gap |
| Training relevance | Average relevance < 3 (with at least one response) |
| Non-placement | A reason accounts for ≥ 25% of cases (analytics); location ≥ 20% (insights) |
| Attrition | Attrition rate ≥ 20% |
| Job retention | Retention < 70% (with at least one employment) |

| Endpoint | Content |
|---|---|
| `skill-gaps`, `skill-gaps/by-course` | Skill gap, training need and relevance, overall and per course |
| `non-placement` | Reasons with shares and the most frequent reason |
| `attrition` | Rate and structured reasons; flags when reason data is missing |
| `training-relevance` | Low (1–2) / Medium (3) / High (4–5) counts |
| `additional-training`, `…/by-course` | Training-need statistics |
| `longitudinal-outcomes` | Completed trainings → completed 30/90-day, 6/12-month follow-ups → employed → retained |
| `programme-improvement` | Key metrics + worded observations |
| `remedial-actions` | Area, triggering metric and suggested action |
| `resource-allocation` | District indicators including completed counts |
| `accountability` | Per course and per provider: completion, placement, employment, retention, relevance, skill gap, attrition, wage growth — unranked |
| `data-quality` | See §15 |
| `summary` | Headline metrics + observations |

---

## 15. Data quality

`GET /api/insights/data-quality` reports counts only:

- trainees missing phone, location, gender or date of birth
- completed trainings without a completion date; trainings missing
  attendance or assessment
- employments missing salary or joining date
- **completed trainings with no outcome yet**
- **employments without wage history, without employer verification, or
  without status history**
- **trainees excluded because consent was withdrawn**
- **trainees involved in possible duplicate registrations**
- follow-ups not completed / not reachable, and the follow-up completion rate

---

## 16. Reliability rules

- A database error in analytics/insights returns **503**, never a
  zero-filled result that could be mistaken for real figures. Other routes
  also convert database errors to 503 without leaking SQL.
- History is append-only: wages, statuses, verifications, attempts and
  outcomes are added, never overwritten.
- Orderings use a date plus the record id as tie-breaker, so history is
  always in a stable chronological order.
- Required columns cannot be cleared with an explicit `null` in PATCH
  requests (`422`).
- Phone numbers accept `+91`, `91` (12 digits) or `0` (11 digits) prefixes;
  a 10-digit number starting with 91 is kept as is.

---

## 17. Configuration

All settings come from `.env` (template: `.env.example`).

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL / Supabase connection string |
| `JWT_SECRET_KEY` | yes | ≥ 32 random characters |
| `JWT_EXPIRE_MINUTES` | no | Token lifetime (default 60) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | yes | Admin login |
| `ANALYST_USERNAME`, `ANALYST_PASSWORD` | no | Analyst login |
| `PUBLIC_BASE_URL` | no | Base of links in messages (default `http://127.0.0.1:8000`) |
| `FOLLOWUP_AUTO_DISPATCH_HOURS` | no | Run the dispatcher every N hours (0 = off) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | no | Email delivery (Gmail: `smtp.gmail.com`, 587, app password) |
| `SMS_WEBHOOK_URL`, `SMS_WEBHOOK_TOKEN` | no | SMS gateway; receives `POST {"to","message"}` |

Generate a secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 18. Running the backend

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # then fill in real values
uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/docs>, click **Authorize**, enter the admin
username and password (leave client id/secret empty).

To open self-report links from a phone on the same Wi-Fi, run
`uvicorn main:app --host 0.0.0.0` and set `PUBLIC_BASE_URL` to
`http://<laptop-IP>:8000`.

---

## 19. Testing

```bash
pytest -q
```

- **127 tests**, about 15 seconds.
- Every test runs on an **in-memory SQLite database** (PostgreSQL sequences
  are emulated), so tests never write to `DATABASE_URL`. Email/SMS
  providers are disabled during tests.
- `TEST_USE_REAL_DB=1 pytest -q` runs the older test modules against
  `DATABASE_URL` instead (insert-only).

| File | Covers |
|---|---|
| `test_phase8_hardening.py` | Access control on every route, login/token validation, fail-closed auth, consent, contact updates, programme/assessment fields, full end-to-end journey with exact figures, all six outcome types, latest-outcome rule, mixed-period wages, attrition, follow-up idempotence, empty database, partial data, 503 on DB error, privacy of aggregates, phone formats |
| `test_gap_features.py` | Dispatch per channel, providers, resend guard, one message per training, outbox, self-report for every outcome type, repeat reports extend the same job, link forgery/reuse, employer confirm/reject, external IDs, duplicate detection, consent exclusion from analytics |
| `test_trainees.py`, `test_training_records.py`, `test_outcomes.py`, `test_followup_tracking.py`, `test_analytics.py`, `test_insights.py`, `test_phase8_validation.py` | Phase 1–7 behaviour and response shapes |

---

## 20. Demo data and demo walkthrough

```bash
python scripts/seed_demo_data.py
```

Inserts 48 trainees through the real API (insert-only, refuses to run
twice) in **Nashik, Kolhapur, Aurangabad, Amravati and Latur** across six
courses and three programmes (PMKVY 4.0, DDU-GKY, State Skill Mission):
all six outcome types, trainees moving from Unemployed to Employed, missed
and not-reachable follow-ups, self-reports, employer-link confirmations,
raises (some quoted as annual CTC), attrition, cross-programme IDs, one
duplicate registration and two consent withdrawals.

Use `?district=Nashik` (or another demo district) for clean demo figures.

**Suggested walkthrough (Swagger):**

1. Authorize as admin; `GET /api/analytics/overview?district=Nashik`
2. `GET /api/analytics/course-performance` and `/district-outcomes` — compare courses and districts
3. `GET /api/analytics/wage-progression` — monthly-normalised growth
4. `GET /api/insights/summary`, `/remedial-actions`, `/accountability`
5. `POST /api/followups/dispatch-due`, then `GET /api/notifications`
6. `GET /api/followups/{id}/self-report-link` → open the link → submit the form
7. Show the new outcome, job, unverified wage and Pending verification
8. `POST /api/employment/{id}/verification-request` → open the employer link → confirm
9. `GET /api/identity/possible-duplicates` and `/api/insights/data-quality`
10. Log in as analyst and show that trainee records return `403`

---

## 21. Problem-statement coverage

| Requirement | Implementation |
|---|---|
| Consent-based records | Required consent, refusal honoured, withdrawal + exclusion from analytics |
| Stable identity despite phone/location changes | `TRN` ID; `PATCH /api/trainees/{id}` |
| Different programme identifiers | External IDs, lookup, duplicate blocking and flagging |
| Programme, course, provider, attendance, assessment, certification | `training_records` |
| Employment, self-employment, apprenticeship, unemployment, further education, not reachable | Outcomes + detail tables |
| 30-day, 90-day, 6-month, 12-month follow-ups | Schedule generator |
| Automated follow-ups | Dispatcher, email/SMS delivery, optional timer |
| Assisted follow-ups | Attempts, outcome updates, outbox, manual links |
| Low-burden tracking | One-minute self-report form; employer confirmation form |
| Employer validation | Verification history, employer link, documents |
| Inconsistent employer reporting | Sources and verification status on every wage; latest verification is authoritative |
| Wage progression | Wage history + monthly normalisation |
| Job retention and attrition | Status history, retention and attrition metrics |
| Cohort / course / provider / district / demographic analytics | `/api/analytics/*` |
| Skill gaps, non-placement reasons, training relevance | Follow-up updates + analytics + insights |
| Accountability, remedial action, resource allocation, programme improvement | `/api/insights/*` |
| Data quality | `/api/insights/data-quality` |
| Privacy | Roles, minimal exposure, aggregate-only analytics, no Aadhaar |

---

## 22. Known limits

- **SMS / WhatsApp** need a gateway account; in India, bulk SMS also
  requires DLT template registration. Until configured, SMS and phone
  follow-ups wait in the outbox for staff.
- **No frontend dashboard**; the API is used through Swagger or a client.
- **Users are configured in `.env`** (one admin, one analyst). A user
  table would be needed for many named staff accounts.
- Self-report and employer links are only reachable from other devices
  when the server is exposed (LAN or deployment) and `PUBLIC_BASE_URL`
  points to it.
- Duplicate detection is rule-based (name + DOB, external IDs); flagged
  records must be reviewed by an admin — there is no automatic merge.
