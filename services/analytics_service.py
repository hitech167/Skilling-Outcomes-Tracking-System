"""
Phase 6 — Analytics & Impact Measurement service.

Pure, read-only query + aggregation logic for the analytics endpoints in
routes/analytics.py. Nothing here writes to the database. No new tables,
models, or sequences are introduced — everything is computed on the fly
from the existing Phase 1-5 tables.

Definitions used throughout (documented once here, not repeated per
function):

- "Placement" = an outcome of type Employed, Self-employed, or
  Apprenticeship.
- Course / provider / district / cohort breakdowns count OUTCOME
  RECORDS tied to COMPLETED training records (one training record has at
  most one outcome in normal use, so this is equivalent to counting
  trainings). "placement_rate" for these breakdowns is
  placed / completed * 100 (completed trainings are the eligible
  population), matching the SIH26135 Phase 6 spec's own example.
- Demographics (gender / age group) count DISTINCT TRAINEES instead,
  since gender/age are trainee-level attributes, not training-level ones
  — a trainee with two completed trainings should not be double-counted
  in a demographic breakdown.
- "Retention" = the trainee's latest known employment_status_history
  entry for an employment record is "Active". Where no history row
  exists yet, the status stored directly on employment_records.
  employment_status is used as a safe fallback (it defaults to "Active"
  when a job starts and nothing has changed it since).
- "Attrition" = the latest known status for an employment record is
  "Left Job" or "Terminated" (or "Left", the Phase 3 employment_records
  spelling of the same thing).
- Outcomes are longitudinal: a training record can collect several
  outcome rows over time (30-day, 6-month, ...). Rates use the LATEST
  outcome per training record (by status_date, then id), so a trainee is
  never counted twice and a later change (e.g. Unemployed -> Employed)
  replaces the earlier state instead of inflating totals.
- Wages: wage_history keeps the salary and salary_period exactly as
  entered. For comparisons, every figure is normalised to a MONTHLY
  equivalent (Annual / 12). Progression needs at least two wage records
  for the same employment; employments with one record contribute to the
  initial/latest averages only.
- Missing data stays missing: an average over zero values is null, not
  0. Rates with an empty eligible population are 0 and always come with
  the eligible count so they can be read correctly.
"""

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy.orm import Session

from database.models import (
    EmploymentRecord,
    EmploymentStatusHistory,
    FollowUp,
    FollowUpOutcomeUpdate,
    NonPlacementRecord,
    Outcome,
    Trainee,
    TrainingRecord,
    WageHistory,
)

PLACEMENT_TYPES = {"Employed", "Self-employed", "Apprenticeship"}
ATTRITION_STATUSES = {"Left Job", "Left", "Terminated"}
SALARY_PERIOD_MONTHS = {"Monthly": 1, "Annual": 12}
AGE_BUCKETS = ["Under 18", "18-24", "25-34", "35-44", "45+", "Unknown"]


# ---------------------------------------------------------------------
# Small safe-math helpers (Part 22 — avoid division-by-zero / None errors)
# ---------------------------------------------------------------------


def _pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _avg(values: list) -> float | None:
    """Average of the non-null values, or None when there is nothing to average."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


# ---------------------------------------------------------------------
# Wage normalisation (stored values are never changed)
# ---------------------------------------------------------------------


def monthly_equivalent(salary, salary_period: str | None) -> float | None:
    """Monthly -> as is, Annual -> / 12. Unknown period or missing salary -> None."""
    if salary is None:
        return None
    months = SALARY_PERIOD_MONTHS.get((salary_period or "").strip().capitalize())
    if months is None:
        return None
    return float(salary) / months


def wage_progression_for(entries: list) -> dict | None:
    """
    Initial vs latest wage for ONE employment, in monthly equivalents.
    `entries` are WageHistory rows; returns None when none are usable.
    change/growth are None when there is only one usable record (no
    progression can be measured); growth is also None if the initial
    wage is 0.
    """
    usable = [
        (w.effective_date, w.id, monthly_equivalent(w.salary, w.salary_period))
        for w in entries
    ]
    usable = sorted((u for u in usable if u[2] is not None), key=lambda u: (u[0], u[1]))
    if not usable:
        return None
    initial = usable[0][2]
    latest = usable[-1][2]
    has_progression = len(usable) >= 2
    return {
        "records": len(usable),
        "initial_monthly": initial,
        "latest_monthly": latest,
        "change_monthly": latest - initial if has_progression else None,
        "growth_percentage": (
            ((latest - initial) / initial) * 100 if has_progression and initial > 0 else None
        ),
    }


# ---------------------------------------------------------------------
# Shared loaders
# ---------------------------------------------------------------------


def _latest_outcome_by_training(db: Session) -> dict:
    """training_record_pk_id -> its most recent Outcome (by status_date, then id)."""
    latest: dict = {}
    for outcome in db.query(Outcome).order_by(
        Outcome.training_record_pk_id, Outcome.status_date.asc(), Outcome.id.asc()
    ):
        latest[outcome.training_record_pk_id] = outcome
    return latest


def _all_training_rows(db: Session):
    """
    Every training record with its LATEST outcome (if any) and its
    trainee. Returns a list of (TrainingRecord, Outcome|None, Trainee) —
    exactly one row per training record, even when several outcomes were
    recorded over time. This is the base dataset for overview / rate /
    course / provider / district / cohort analytics.
    """
    latest_outcomes = _latest_outcome_by_training(db)
    rows = (
        db.query(TrainingRecord, Trainee)
        .join(Trainee, TrainingRecord.trainee_pk_id == Trainee.id)
        .all()
    )
    return [(tr, latest_outcomes.get(tr.id), trainee) for tr, trainee in rows]


def _trainee_outcome_types(db: Session) -> dict:
    """trainee_pk_id -> set of latest outcome_types across their COMPLETED trainings."""
    latest_outcomes = _latest_outcome_by_training(db)
    completed = db.query(TrainingRecord).filter(TrainingRecord.status == "Completed").all()
    mapping = defaultdict(set)
    for tr in completed:
        outcome = latest_outcomes.get(tr.id)
        if outcome is not None:
            mapping[tr.trainee_pk_id].add(outcome.outcome_type)
    return mapping


def _trainees_with_completed_training(db: Session) -> set:
    return {
        pk
        for (pk,) in db.query(TrainingRecord.trainee_pk_id)
        .filter(TrainingRecord.status == "Completed")
        .distinct()
    }


def _latest_employment_status_rows(db: Session) -> dict:
    """
    employment_pk_id -> the latest EmploymentStatusHistory row for that
    employment (by status_date, then id). Employments with no history
    row at all are simply absent from the dict — callers fall back to
    employment_records.employment_status for those.
    """
    history_rows = (
        db.query(EmploymentStatusHistory)
        .order_by(
            EmploymentStatusHistory.employment_pk_id,
            EmploymentStatusHistory.status_date.asc(),
            EmploymentStatusHistory.id.asc(),
        )
        .all()
    )
    latest: dict = {}
    for row in history_rows:
        # Ascending order per employment_pk_id means the last write for
        # each key ends up being the most recent row.
        latest[row.employment_pk_id] = row
    return latest


def _resolve_latest_status(
    employment: EmploymentRecord, latest_rows: dict
) -> str:
    row = latest_rows.get(employment.id)
    if row is not None:
        return row.employment_status
    return employment.employment_status


# ---------------------------------------------------------------------
# Part 2/3/4 — overview, placement rate, employment rate
# ---------------------------------------------------------------------


def _outcome_type_counts(rows, completed_only: bool = True) -> Counter:
    counts = Counter()
    for tr, outcome, _trainee in rows:
        if completed_only and tr.status != "Completed":
            continue
        if outcome is not None:
            counts[outcome.outcome_type] += 1
    return counts


def get_overview(db: Session, district: str | None = None) -> dict:
    rows = _all_training_rows(db)

    if district:
        rows = [r for r in rows if r[2].district == district]
        total_trainees = db.query(Trainee).filter(Trainee.district == district).count()
        employments = (
            db.query(EmploymentRecord)
            .join(Trainee, EmploymentRecord.trainee_pk_id == Trainee.id)
            .filter(Trainee.district == district)
            .all()
        )
        latest_rows = _latest_employment_status_rows(db)
        employed_count = len(employments)
        retained = sum(1 for emp in employments if _resolve_latest_status(emp, latest_rows) == "Active")
        retention_rate = _pct(retained, employed_count)
    else:
        total_trainees = db.query(Trainee).count()
        retention = get_retention_rate(db)
        retention_rate = retention["retention_rate"]

    total_training_records = len(rows)

    status_counts = Counter(tr.status for tr, _o, _t in rows)
    completed = status_counts.get("Completed", 0)

    outcome_counts = _outcome_type_counts(rows, completed_only=True)
    employed = outcome_counts.get("Employed", 0)
    self_employed = outcome_counts.get("Self-employed", 0)
    apprenticeship = outcome_counts.get("Apprenticeship", 0)
    unemployed = outcome_counts.get("Unemployed", 0)
    further_education = outcome_counts.get("Further Education", 0)
    not_reachable = outcome_counts.get("Not Reachable", 0)

    placed = employed + self_employed + apprenticeship

    return {
        "total_trainees": total_trainees,
        "total_training_records": total_training_records,
        "enrolled_trainings": status_counts.get("Enrolled", 0),
        "ongoing_trainings": status_counts.get("Ongoing", 0),
        "completed_trainings": completed,
        "dropped_trainings": status_counts.get("Dropped", 0),
        "employed_trainees": employed,
        "self_employed_trainees": self_employed,
        "apprenticeship_trainees": apprenticeship,
        "unemployed_trainees": unemployed,
        "further_education_trainees": further_education,
        "not_reachable_trainees": not_reachable,
        "placed_trainees": placed,
        "placement_rate": _pct(placed, completed),
        "employment_rate": _pct(employed, completed),
        "retention_rate": retention_rate,
    }


def get_placement_rate(db: Session) -> dict:
    rows = _all_training_rows(db)
    completed = sum(1 for tr, _o, _t in rows if tr.status == "Completed")
    outcome_counts = _outcome_type_counts(rows, completed_only=True)
    placed = sum(outcome_counts.get(t, 0) for t in PLACEMENT_TYPES)
    return {
        "eligible_trainees": completed,
        "placed_trainees": placed,
        "placement_rate": _pct(placed, completed),
    }


def get_employment_rate(db: Session) -> dict:
    rows = _all_training_rows(db)
    completed = sum(1 for tr, _o, _t in rows if tr.status == "Completed")
    outcome_counts = _outcome_type_counts(rows, completed_only=True)
    employed = outcome_counts.get("Employed", 0)
    return {
        "eligible_trainees": completed,
        "employed_trainees": employed,
        "employment_rate": _pct(employed, completed),
    }


# ---------------------------------------------------------------------
# Part 5 — retention rate
# ---------------------------------------------------------------------


def get_retention_rate(db: Session) -> dict:
    employments = db.query(EmploymentRecord).all()
    latest_rows = _latest_employment_status_rows(db)

    employed_trainees = len(employments)
    retained = sum(
        1
        for emp in employments
        if _resolve_latest_status(emp, latest_rows) == "Active"
    )

    return {
        "employed_trainees": employed_trainees,
        "retained_trainees": retained,
        "retention_rate": _pct(retained, employed_trainees),
        "definition": "Latest known employment status = Active",
    }


# ---------------------------------------------------------------------
# Part 6 — wage progression
# ---------------------------------------------------------------------


def get_wage_progression(db: Session) -> dict:
    """
    First vs latest wage per employment (chronological by effective_date),
    with every salary normalised to a monthly equivalent so Monthly and
    Annual records can be compared. Salary figures returned are monthly.
    """
    by_employment = defaultdict(list)
    for w in db.query(WageHistory).all():
        by_employment[w.employment_pk_id].append(w)

    initial_salaries = []
    latest_salaries = []
    changes = []
    growth_percentages = []

    for entries in by_employment.values():
        progression = wage_progression_for(entries)
        if progression is None:
            continue
        initial_salaries.append(progression["initial_monthly"])
        latest_salaries.append(progression["latest_monthly"])
        changes.append(progression["change_monthly"])
        growth_percentages.append(progression["growth_percentage"])

    return {
        "employment_records": db.query(EmploymentRecord).count(),
        "employment_records_with_wage_data": len(initial_salaries),
        "employment_records_with_wage_progression": sum(1 for c in changes if c is not None),
        "salary_basis": "Monthly (Annual salaries divided by 12)",
        "average_initial_salary": _avg(initial_salaries),
        "average_latest_salary": _avg(latest_salaries),
        "average_salary_change": _avg(changes),
        "average_salary_growth_percentage": _avg(growth_percentages),
    }


# ---------------------------------------------------------------------
# Parts 7/8/9 — course / provider / district breakdowns
# ---------------------------------------------------------------------


def _group_performance(rows, key_fn) -> list:
    """
    Shared grouping logic for course/provider/district performance.
    `key_fn` extracts the group key (course_name, provider_name, or
    trainee.district) from a (TrainingRecord, Outcome|None, Trainee) row.
    """
    groups: dict = defaultdict(lambda: {"total": 0, "completed": 0, "outcomes": Counter()})

    for tr, outcome, trainee in rows:
        key = key_fn(tr, trainee)
        if key is None:
            continue
        bucket = groups[key]
        bucket["total"] += 1
        if tr.status == "Completed":
            bucket["completed"] += 1
            if outcome is not None:
                bucket["outcomes"][outcome.outcome_type] += 1

    result = []
    for key, bucket in sorted(groups.items()):
        outcomes = bucket["outcomes"]
        employed = outcomes.get("Employed", 0)
        self_employed = outcomes.get("Self-employed", 0)
        apprenticeship = outcomes.get("Apprenticeship", 0)
        unemployed = outcomes.get("Unemployed", 0)
        placed = employed + self_employed + apprenticeship
        result.append(
            {
                "name": key,
                "total_trainees": bucket["total"],
                "completed": bucket["completed"],
                "placed": placed,
                "employed": employed,
                "self_employed": self_employed,
                "apprenticeship": apprenticeship,
                "unemployed": unemployed,
                "placement_rate": _pct(placed, bucket["completed"]),
            }
        )
    return result


def get_course_performance(db: Session) -> list:
    rows = _all_training_rows(db)
    grouped = _group_performance(rows, key_fn=lambda tr, _t: tr.course_name)
    return [{"course_name": g["name"], **{k: v for k, v in g.items() if k != "name"}} for g in grouped]


def get_provider_performance(db: Session) -> list:
    rows = _all_training_rows(db)
    grouped = _group_performance(rows, key_fn=lambda tr, _t: tr.provider_name)
    return [{"provider_name": g["name"], **{k: v for k, v in g.items() if k != "name"}} for g in grouped]


def get_district_outcomes(db: Session) -> list:
    rows = _all_training_rows(db)
    grouped = _group_performance(rows, key_fn=lambda _tr, trainee: trainee.district)
    return [{"district": g["name"], **{k: v for k, v in g.items() if k != "name"}} for g in grouped]


# ---------------------------------------------------------------------
# Part 10 — demographics (distinct-trainee based, see module docstring)
# ---------------------------------------------------------------------


def _age_bucket(dob: date, today: date) -> str:
    if dob is None:
        return "Unknown"
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if years < 18:
        return "Under 18"
    if years <= 24:
        return "18-24"
    if years <= 34:
        return "25-34"
    if years <= 44:
        return "35-44"
    return "45+"


def get_demographics(db: Session) -> dict:
    """
    placement_rate here = trainees placed via a completed training /
    trainees with at least one completed training, so trainees still in
    training are not counted as "not placed".
    """
    trainees = db.query(Trainee).all()
    outcome_types_by_trainee = _trainee_outcome_types(db)
    completed_trainees = _trainees_with_completed_training(db)
    today = date.today()

    def _summarize(bucket_trainees: list) -> dict:
        total = len(bucket_trainees)
        completed = sum(1 for t in bucket_trainees if t.id in completed_trainees)
        employed = self_employed = apprenticeship = unemployed = placed = 0
        for t in bucket_trainees:
            types = outcome_types_by_trainee.get(t.id, set())
            if "Employed" in types:
                employed += 1
            if "Self-employed" in types:
                self_employed += 1
            if "Apprenticeship" in types:
                apprenticeship += 1
            if "Unemployed" in types:
                unemployed += 1
            if types & PLACEMENT_TYPES:
                placed += 1
        return {
            "total_trainees": total,
            "completed_trainees": completed,
            "employed": employed,
            "self_employed": self_employed,
            "apprenticeship": apprenticeship,
            "unemployed": unemployed,
            "placement_rate": _pct(placed, completed),
        }

    # Gender distribution
    by_gender = defaultdict(list)
    for t in trainees:
        by_gender[t.gender if t.gender and t.gender.strip() else "Unknown"].append(t)
    gender_distribution = [
        {"gender": gender, **_summarize(members)}
        for gender, members in sorted(by_gender.items())
    ]

    # Age groups
    by_age = defaultdict(list)
    for t in trainees:
        by_age[_age_bucket(t.dob, today)].append(t)
    age_groups = []
    for bucket in AGE_BUCKETS:
        members = by_age.get(bucket, [])
        if not members and bucket == "Unknown":
            continue
        summary = _summarize(members)
        age_groups.append(
            {
                "age_group": bucket,
                "total_trainees": summary["total_trainees"],
                "completed_trainees": summary["completed_trainees"],
                "employed": summary["employed"],
                "placed": summary["employed"]
                + summary["self_employed"]
                + summary["apprenticeship"],
                "unemployed": summary["unemployed"],
                "placement_rate": summary["placement_rate"],
            }
        )

    return {"gender_distribution": gender_distribution, "age_groups": age_groups}


# ---------------------------------------------------------------------
# Part 11 — non-placement reasons
# ---------------------------------------------------------------------


def get_non_placement_reasons(db: Session) -> list:
    records = db.query(NonPlacementRecord).all()
    total = len(records)
    counts = Counter(r.reason_category for r in records)
    return [
        {"reason": reason, "count": count, "percentage": _pct(count, total)}
        for reason, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


# ---------------------------------------------------------------------
# Part 12 — attrition
# ---------------------------------------------------------------------


def get_attrition(db: Session) -> dict:
    employments = db.query(EmploymentRecord).all()
    latest_rows = _latest_employment_status_rows(db)

    total = len(employments)
    reason_counts = Counter()
    attrition_count = 0
    missing_reason_count = 0

    for emp in employments:
        row = latest_rows.get(emp.id)
        status = row.employment_status if row is not None else emp.employment_status
        if status in ATTRITION_STATUSES:
            attrition_count += 1
            reason = row.reason if row is not None and row.reason else None
            if reason:
                reason_counts[reason] += 1
            else:
                missing_reason_count += 1

    reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    if missing_reason_count:
        reasons.append({"reason": "Not Specified", "count": missing_reason_count})

    note = (
        "All attrition reasons recorded from official status records."
        if missing_reason_count == 0
        else f"{missing_reason_count} record(s) did not have a specific attrition reason specified."
    )

    return {
        "total_employment_records": total,
        "attrition_records": attrition_count,
        "attrition_rate": _pct(attrition_count, total),
        "reasons": reasons,
        "reason_data_complete": missing_reason_count == 0,
        "note": note,
    }


# ---------------------------------------------------------------------
# Part 13 — skill gaps
# ---------------------------------------------------------------------


def get_skill_gaps(db: Session) -> dict:
    updates = db.query(FollowUpOutcomeUpdate).all()
    total = len(updates)
    skill_gap = sum(1 for u in updates if u.skill_gap is True)
    additional_training = sum(1 for u in updates if u.additional_training_needed is True)
    return {
        "followups_with_skill_gap": skill_gap,
        "additional_training_needed": additional_training,
        "skill_gap_percentage": _pct(skill_gap, total),
    }


# ---------------------------------------------------------------------
# Part 14 — training relevance
# ---------------------------------------------------------------------


def get_training_relevance(db: Session) -> dict:
    updates = db.query(FollowUpOutcomeUpdate).all()
    ratings = [u.training_relevance for u in updates if u.training_relevance is not None]
    total = len(ratings)
    counts = Counter(ratings)
    return {
        "total_responses": total,
        "average_relevance": _avg(ratings),
        "ratings": {str(i): counts.get(i, 0) for i in range(1, 6)},
    }


# ---------------------------------------------------------------------
# Part 15 — cohort analytics
# ---------------------------------------------------------------------


def get_cohort_analytics(db: Session) -> list:
    """
    Cohort = the year-month a training was completed (end_date), among
    COMPLETED training records only — a training with no completion date
    yet has no cohort to belong to. Because of this, total_trainees and
    completed are always equal within this implementation; see the
    module docstring / README notes for the reasoning.
    """
    rows = _all_training_rows(db)
    groups: dict = defaultdict(lambda: Counter())
    group_totals: dict = defaultdict(int)

    for tr, outcome, _trainee in rows:
        if tr.status != "Completed" or tr.end_date is None:
            continue
        cohort_key = tr.end_date.strftime("%Y-%m")
        group_totals[cohort_key] += 1
        if outcome is not None:
            groups[cohort_key][outcome.outcome_type] += 1

    result = []
    for cohort_key in sorted(group_totals):
        completed = group_totals[cohort_key]
        outcomes = groups[cohort_key]
        employed = outcomes.get("Employed", 0)
        self_employed = outcomes.get("Self-employed", 0)
        apprenticeship = outcomes.get("Apprenticeship", 0)
        unemployed = outcomes.get("Unemployed", 0)
        placed = employed + self_employed + apprenticeship
        result.append(
            {
                "cohort": cohort_key,
                "total_trainees": completed,
                "completed": completed,
                "placed": placed,
                "employed": employed,
                "self_employed": self_employed,
                "apprenticeship": apprenticeship,
                "unemployed": unemployed,
                "placement_rate": _pct(placed, completed),
            }
        )
    return result


# ---------------------------------------------------------------------
# Part 16 — accountability
# ---------------------------------------------------------------------


def get_accountability(db: Session) -> dict:
    rows = _all_training_rows(db)
    total_training_records = len(rows)
    completed = sum(1 for tr, _o, _t in rows if tr.status == "Completed")

    placement = get_placement_rate(db)
    employment = get_employment_rate(db)
    retention = get_retention_rate(db)
    relevance = get_training_relevance(db)
    skill_gaps = get_skill_gaps(db)
    non_placement_count = db.query(NonPlacementRecord).count()
    attrition = get_attrition(db)
    wages = get_wage_progression(db)

    return {
        "total_trainees": db.query(Trainee).count(),
        "completion_rate": _pct(completed, total_training_records),
        "placement_rate": placement["placement_rate"],
        "employment_rate": employment["employment_rate"],
        "retention_rate": retention["retention_rate"],
        "average_training_relevance": relevance["average_relevance"],
        "skill_gap_percentage": skill_gaps["skill_gap_percentage"],
        "non_placement_count": non_placement_count,
        "attrition_rate": attrition["attrition_rate"],
        "average_salary_growth_percentage": wages["average_salary_growth_percentage"],
        "definitions": {
            "completion_rate": "Completed training records divided by total training records",
            "placement_rate": "Placed trainees (Employed, Self-employed, Apprenticeship) divided by completed trainings",
            "employment_rate": "Employed trainees divided by completed trainings",
            "retention_rate": "Active employees divided by total employment records",
            "average_training_relevance": "Average rating of training relevance on scale 1 to 5 from follow-ups",
            "skill_gap_percentage": "Percentage of follow-up updates reporting a skill gap",
            "attrition_rate": "Percentage of employment records whose latest status is Left Job or Terminated",
            "average_salary_growth_percentage": "Average percentage growth from first to latest wage record per employment (monthly-normalised; needs 2+ wage records)",
        },
    }


# ---------------------------------------------------------------------
# Part 17 — remedial insights (rule-based, no AI/ML)
# ---------------------------------------------------------------------


def get_remedial_insights(db: Session) -> list:
    insights = []

    skill_gaps = get_skill_gaps(db)
    if skill_gaps["skill_gap_percentage"] >= 25:
        insights.append(
            {
                "area": "Skill Gap",
                "metric": skill_gaps["skill_gap_percentage"],
                "insight": (
                    f"{skill_gaps['skill_gap_percentage']}% of recorded follow-ups "
                    "reported a skill gap, indicating a need to review course "
                    "content and additional training support."
                ),
            }
        )

    relevance = get_training_relevance(db)
    if relevance["total_responses"] > 0 and relevance["average_relevance"] < 3:
        insights.append(
            {
                "area": "Training Relevance",
                "metric": relevance["average_relevance"],
                "insight": (
                    f"Average reported training relevance is "
                    f"{relevance['average_relevance']}/5, indicating that course "
                    "relevance should be reviewed."
                ),
            }
        )

    for reason in get_non_placement_reasons(db):
        if reason["percentage"] >= 25:
            insights.append(
                {
                    "area": f"Non-Placement — {reason['reason']}",
                    "metric": reason["percentage"],
                    "insight": (
                        f"{reason['reason']} accounts for {reason['percentage']}% of "
                        "recorded non-placement cases, indicating it is a "
                        "frequently reported barrier."
                    ),
                }
            )

    attrition = get_attrition(db)
    if attrition["attrition_rate"] >= 20:
        insights.append(
            {
                "area": "Attrition",
                "metric": attrition["attrition_rate"],
                "insight": (
                    f"{attrition['attrition_rate']}% of employment records show the "
                    "trainee has since left or been terminated, indicating job "
                    "retention support may be needed."
                ),
            }
        )

    return insights


# ---------------------------------------------------------------------
# Part 18 — resource allocation
# ---------------------------------------------------------------------


def get_resource_allocation(db: Session) -> list:
    trainees = db.query(Trainee).all()
    outcome_types_by_trainee = _trainee_outcome_types(db)

    non_placement_by_trainee = Counter(
        trainee_pk_id
        for (trainee_pk_id,) in db.query(NonPlacementRecord.trainee_pk_id).all()
    )

    followup_updates = db.query(FollowUpOutcomeUpdate).all()
    skill_gap_by_trainee = Counter(
        u.trainee_pk_id for u in followup_updates if u.skill_gap is True
    )
    additional_training_by_trainee = Counter(
        u.trainee_pk_id for u in followup_updates if u.additional_training_needed is True
    )

    latest_rows = _latest_employment_status_rows(db)
    employments = db.query(EmploymentRecord).all()
    attrition_by_trainee = Counter()
    for emp in employments:
        status = _resolve_latest_status(emp, latest_rows)
        if status in ATTRITION_STATUSES:
            attrition_by_trainee[emp.trainee_pk_id] += 1

    by_district = defaultdict(
        lambda: {
            "trainee_count": 0,
            "unemployed_count": 0,
            "skill_gap_count": 0,
            "non_placement_count": 0,
            "attrition_count": 0,
            "additional_training_needed": 0,
        }
    )

    for t in trainees:
        bucket = by_district[t.district]
        bucket["trainee_count"] += 1
        if "Unemployed" in outcome_types_by_trainee.get(t.id, set()):
            bucket["unemployed_count"] += 1
        bucket["skill_gap_count"] += skill_gap_by_trainee.get(t.id, 0)
        bucket["non_placement_count"] += non_placement_by_trainee.get(t.id, 0)
        bucket["attrition_count"] += attrition_by_trainee.get(t.id, 0)
        bucket["additional_training_needed"] += additional_training_by_trainee.get(t.id, 0)

    return [
        {"district": district, **stats}
        for district, stats in sorted(by_district.items())
    ]
