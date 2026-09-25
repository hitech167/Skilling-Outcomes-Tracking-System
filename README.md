# SIH26135 — Longitudinal Skilling Outcomes & Impact Measurement System (Backend)

FastAPI + SQLAlchemy + PostgreSQL/Supabase backend that follows a trainee
from consent and training through follow-ups, outcomes, employer
verification, wages and job retention, and turns that into aggregated,
privacy-safe analytics and rule-based insights.

| Phase | Module |
|---|---|
| 1 | Trainee registration + consent, stable trainee ID, contact updates |
| 2 | Training: programme, course, provider, attendance, assessment, certification |
| 3 | Outcomes: Employed / Self-employed / Apprenticeship / Unemployed / Further Education / Not Reachable (+ detail records, non-placement reasons) |
| 4 | Employer verification, wage history, employment-status history (retention) |
| 5 | 30-day / 90-day / 6-month / 12-month follow-ups, contact attempts, assisted outcome updates |
| 6 | Analytics (`/api/analytics/*`) |
| 7 | Insights (`/api/insights/*`) |
| 8 | Integration, validation, JWT access control, automated contact + self-report / employer links, cross-programme IDs |

## 1. Install

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure `.env`

```bash
copy .env.example .env         # macOS/Linux: cp .env.example .env
```

Fill in `DATABASE_URL`, `JWT_SECRET_KEY` (32+ random characters) and the
admin/analyst credentials. `.env` is git-ignored — never commit it.

## 3. Run

```bash
uvicorn main:app --reload
```

On startup the app creates missing tables and ID sequences and adds any
missing nullable columns (`CREATE ... IF NOT EXISTS` / `ADD COLUMN IF NOT
EXISTS`). It never drops or rewrites existing data.

Swagger: <http://127.0.0.1:8000/docs> — click **Authorize** and log in.

## 4. Authentication & roles

`POST /api/auth/token` (form fields `username`, `password`) returns a
bearer token. Users are configured in `.env`; there is no user table.

| Role | Can access |
|---|---|
| `admin` | Everything: trainees, contact details, training, outcomes, follow-ups, employment, employer verification, wages, status history, analytics, insights |
| `analyst` | `/api/analytics/*` and `/api/insights/*` only (aggregated, no personal data) |
| public | `/`, `/api/system/health`, `/docs`, `/api/auth/token`, and the signed self-report / employer-confirmation links |

If `JWT_SECRET_KEY` is missing or too short, the API fails closed (503 on
protected endpoints).

## 5. Privacy & consent

- `trainee_id` (TRN000001…) is the permanent identity; phone/location can be
  changed with `PATCH /api/trainees/{id}` without breaking history. Trainees
  can also change their own phone / location from their follow-up link
  (`PATCH /api/self-report/{token}/contact`, no login). Every change is
  kept in `trainee_contact_history` (`GET /api/trainees/{id}/contact-history`).
- Consent is audited: every grant / withdrawal is logged in
  `trainee_consent_history` (source `registration` / `admin` / `self`, method
  such as *Paper form*, and who recorded it) - `GET /api/trainees/{id}/consent-history`.
  Staff can record `consent_method` / `consent_recorded_by` at registration, and a
  trainee can withdraw or re-grant their own consent from their link
  (`POST /api/self-report/{token}/consent`, no login).
- Registration requires `consent_given: true`; an explicit `false` for
  `consent_analytics` / `consent_privacy_notice` is refused, never ignored.
- `POST /api/trainees/{id}/consent` withdraws or re-grants consent. With
  consent withdrawn, follow-up scheduling, contact attempts, automated
  messages and self-reports are blocked, and the trainee is **excluded from
  every analytics / insights figure**. Records are kept, not deleted, and
  re-granting consent restores them. Data quality reports how many trainees
  are excluded.
- `GET /api/trainees/{id}` never returns phone, email or DOB. Contact
  details for assisted follow-ups are at `GET /api/trainees/{id}/contact`
  (admin only).
- Analytics and insights return counts, rates and averages only — no names,
  contact details, DOBs, trainee IDs or employer contacts.

## 6. Low-burden, automated follow-up

1. `POST /api/followups/generate/{training_id}` creates the 30/90-day and
   6/12-month schedule for a completed training (safe to repeat).
2. `POST /api/followups/dispatch-due` (or set `FOLLOWUP_AUTO_DISPATCH_HOURS`)
   messages every due follow-up on the trainee's preferred channel with a
   personal **self-report link**:
   - Email is sent by SMTP when `SMTP_HOST` is configured.
   - SMS goes to the gateway at `SMS_WEBHOOK_URL` when configured.
   - Phone preferences, and any channel without a provider, are **queued** in
     the outbox (`GET /api/notifications?status=Queued`) for staff, who
     mark them done with `POST /api/notifications/{id}/mark-sent`.
   - Trainees are not messaged again within 7 days, and never after
     withdrawing consent.
3. The trainee opens `/self-report/{token}` (a mobile form, no login) and
   says what they are doing now. That one submission records the outcome,
   the job / business / apprenticeship details, the wage (as *Trainee,
   Unverified*), relevance / skill-gap answers, a successful contact
   attempt, and completes the follow-up. Self-reported jobs get a *Pending*
   employer verification, so they are never treated as verified.
4. Staff can still do everything by hand (assisted follow-up): contact
   attempts, complete / missed / not reachable, outcome updates.
   `GET /api/followups/{id}/self-report-link` gives a link to share on WhatsApp.

**Employer validation without a portal account:**
`POST /api/employment/{id}/verification-request` creates a Pending
verification and a link (emailed if the contact is an email address and
SMTP is set up). The employer opens `/employer-verify/{token}` and confirms
or rejects the employment, with current status and salary. That marks it
*Verified* or *Rejected* via *Employer Portal* and records an
*Employer, Verified* wage.

`POST /api/verifications/remind-pending` re-sends the link to employers who
have not answered for 7 days. After 3 requests with no answer the
verification becomes *Unable to Verify* ("Employer unresponsive"). It only
runs when called, so schedule it (cron) if you want it automatic.

All links are signed, expire after 30 days, and can never be used as a login.
Follow-up and verification submissions work once only; the contact-update
route can be used repeatedly until the link expires.

**External employment signals:** `POST /api/employment-signals/import` (admin,
multipart CSV + `source`, optional `dry_run`) loads placements from an outside
source such as an EPFO/ESIC extract or a job-portal export. Columns:
`trainee_id` | `phone` | `external_id` (`TYPE:VALUE`), `employer_name`,
`start_date` (YYYY-MM-DD), optional `job_role`, `monthly_salary`, `reference`.
Matched, consenting trainees get an Employed outcome, employment record, wage
point and an employer verification marked *Verified* by *Document*. Existing
employers are never duplicated (a Pending verification is just resolved), and a
bad row is reported without failing the file.

## 7. Cross-programme identity

- `trainee_id` is the one stable identity. IDs from other programmes
  (Skill India Digital ID, PMKVY / DDU-GKY candidate IDs, state scheme
  numbers) are linked with `POST /api/trainees/{id}/external-ids`, or
  passed as `external_ids` at registration.
- `GET /api/identity/lookup?id_type=...&id_value=...` finds the trainee
  for an ID used by another programme.
- A registration that reuses an already-linked external ID is refused
  (409, naming the existing trainee). Same name + date of birth is
  returned as `possible_duplicates` and listed at
  `GET /api/identity/possible-duplicates`. Matches are flagged, never
  merged automatically.
- Aadhaar numbers are rejected and never stored.

## 8. Metric definitions

| Metric | Definition |
|---|---|
| Placement rate | (Employed + Self-employed + Apprenticeship) ÷ completed trainings |
| Employment rate | Employed ÷ completed trainings |
| Outcome used | The **latest** outcome per training record (by `status_date`), so a training is never double-counted and later updates replace earlier states |
| Retention rate | Employment records whose latest status is `Active` ÷ all employment records |
| Attrition rate | Employment records whose latest status is `Left Job`/`Left`/`Terminated` ÷ all employment records |
| Wage progression | First vs latest wage record per employment by `effective_date`. Stored salary and period are kept as entered; for comparison each figure is normalised to monthly (Annual ÷ 12). Growth needs 2+ wage records |
| Demographic placement rate | Placed trainees ÷ trainees with at least one completed training |

Missing data stays missing: averages with no data are `null`, lists are
`[]`, and rates over an empty population are `0` alongside the population
count. A database error returns 503 — never zero-filled figures.
`/api/insights/data-quality` reports gaps such as completed trainings
without an outcome or employments without wage, verification or status
history.

## 9. Demo data

```bash
python scripts/seed_demo_data.py
```

Adds 48 realistic trainees through the API: all six outcome types,
follow-ups (completed, missed, not reachable, self-reported, and some still
due for the dispatcher), employer confirmations, wage raises (some quoted as
annual CTC), attrition, cross-programme IDs, one duplicate registration and
two consent withdrawals. It only inserts, and refuses to run twice.

Demo trainees live in **Nashik, Kolhapur, Aurangabad, Amravati and Latur**,
so `GET /api/analytics/overview?district=Nashik` shows demo data only.

## 10. Tests

```bash
pytest -q
```

All tests run on a throwaway in-memory SQLite database, so they never
write to `DATABASE_URL`, and the whole suite takes about 15 seconds.
`TEST_USE_REAL_DB=1 pytest -q` runs the older modules against
`DATABASE_URL` instead; those modules only insert rows.
