"""
Phase 7 — Skill Gaps, Attrition & Improvement Intelligence service.

Deliberately built ON TOP OF services/analytics_service.py (Phase 6)
rather than re-deriving the same base numbers: overall placement,
employment, retention, non-placement, attrition, skill-gap and
training-relevance figures are imported and reused as-is. This module
only adds what Phase 6 did not already compute:

- by-course / by-provider breakdowns of follow-up (skill gap /
  additional training / relevance) and employment (retention /
  attrition / wage growth) data
- longitudinal follow-up-stage counts
- rule-based, worded observations and remedial-action suggestions
- data-quality (missing-field) counts
- a combined summary

Nothing here writes to the database. No new tables/models/sequences.
"""

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    EmployerVerification,
    EmploymentRecord,
    FollowUp,
    FollowUpOutcomeUpdate,
    Outcome,
    Trainee,
    TrainingRecord,
)
from services import analytics_service, identity_service
from services.analytics_service import (
    ATTRITION_STATUSES,
    _all_training_rows,
    _avg,
    _cached,
    _employment_rows,
    _followup_update_rows,
    _latest_employment_status_rows,
    _latest_outcome_by_training,
    _pct,
    _resolve_latest_status,
    _wages_by_employment,
    wage_progression_for,
)

FOLLOWUP_TYPES = ("30_DAY", "90_DAY", "6_MONTH", "12_MONTH")


# ---------------------------------------------------------------------
# Part 2 — skill gaps (overall), reusing Phase 6's get_skill_gaps
# ---------------------------------------------------------------------


def get_skill_gaps_overview(db: Session) -> dict:
    updates = _followup_update_rows(db)
    total = len(updates)
    skill_gap = sum(1 for u in updates if u.skill_gap is True)
    additional_training = sum(1 for u in updates if u.additional_training_needed is True)
    relevance_values = [u.training_relevance for u in updates if u.training_relevance is not None]

    return {
        "total_followups": total,
        "followups_with_skill_gap": skill_gap,
        "skill_gap_percentage": _pct(skill_gap, total),
        "additional_training_needed": additional_training,
        "additional_training_percentage": _pct(additional_training, total),
        "average_training_relevance": _avg(relevance_values),
    }


# ---------------------------------------------------------------------
# Shared: follow-up-outcome-update rows joined with course/provider
# ---------------------------------------------------------------------


def _followup_update_rows_with_group(db: Session):
    """Every recorded follow-up update's answers with its training's course_name / provider_name."""
    return _cached(
        db,
        "followup_update_rows_with_group",
        lambda: db.query(
            FollowUpOutcomeUpdate.skill_gap,
            FollowUpOutcomeUpdate.additional_training_needed,
            FollowUpOutcomeUpdate.training_relevance,
            TrainingRecord.course_name,
            TrainingRecord.provider_name,
        )
        .join(FollowUp, FollowUpOutcomeUpdate.followup_pk_id == FollowUp.id)
        .join(TrainingRecord, FollowUp.training_record_pk_id == TrainingRecord.id)
        .all(),
    )


def _group_followup_stats(rows, key_is_course: bool) -> dict:
    groups = defaultdict(lambda: {"total": 0, "skill_gap": 0, "additional_training": 0, "relevance": []})
    for update in rows:
        key = update.course_name if key_is_course else update.provider_name
        bucket = groups[key]
        bucket["total"] += 1
        if update.skill_gap is True:
            bucket["skill_gap"] += 1
        if update.additional_training_needed is True:
            bucket["additional_training"] += 1
        if update.training_relevance is not None:
            bucket["relevance"].append(update.training_relevance)

    result = {}
    for key, bucket in groups.items():
        result[key] = {
            "total_followups": bucket["total"],
            "skill_gap_count": bucket["skill_gap"],
            "skill_gap_percentage": _pct(bucket["skill_gap"], bucket["total"]),
            "additional_training_count": bucket["additional_training"],
            "additional_training_percentage": _pct(bucket["additional_training"], bucket["total"]),
            "average_training_relevance": _avg(bucket["relevance"]),
        }
    return result


# ---------------------------------------------------------------------
# Part 3 — skill gaps by course
# ---------------------------------------------------------------------


def get_skill_gaps_by_course(db: Session) -> list:
    rows = _followup_update_rows_with_group(db)
    grouped = _group_followup_stats(rows, key_is_course=True)
    return [
        {"course_name": course_name, **stats}
        for course_name, stats in sorted(grouped.items())
    ]


# ---------------------------------------------------------------------
# Part 4 — non-placement analysis (reuses Phase 6's reason breakdown)
# ---------------------------------------------------------------------


def get_non_placement_analysis(db: Session) -> dict:
    reasons = analytics_service.get_non_placement_reasons(db)
    total = sum(r["count"] for r in reasons)
    most_frequent = reasons[0]["reason"] if reasons else None
    return {"total_records": total, "reasons": reasons, "most_frequent_reason": most_frequent}


# ---------------------------------------------------------------------
# Part 5 — attrition analysis (reuses Phase 6's get_attrition, reshaped)
# ---------------------------------------------------------------------


def get_attrition_analysis(db: Session) -> dict:
    base = analytics_service.get_attrition(db)
    total = base["attrition_records"]
    reasons_with_pct = [
        {
            "reason": r["reason"],
            "count": r["count"],
            "percentage": _pct(r["count"], total),
        }
        for r in base["reasons"]
        if r["reason"] != "Not Specified"
    ]
    return {
        "total_employment_records": base["total_employment_records"],
        "attrition_records": base["attrition_records"],
        "attrition_rate": base["attrition_rate"],
        "reasons": reasons_with_pct,
        "reason_data_available": bool(reasons_with_pct),
    }


# ---------------------------------------------------------------------
# Part 6 — training relevance insights (buckets Phase 6's ratings)
# ---------------------------------------------------------------------


def get_training_relevance_insights(db: Session) -> dict:
    base = analytics_service.get_training_relevance(db)
    ratings = base["ratings"]
    low = ratings.get("1", 0) + ratings.get("2", 0)
    medium = ratings.get("3", 0)
    high = ratings.get("4", 0) + ratings.get("5", 0)
    return {
        "total_responses": base["total_responses"],
        "average_rating": base["average_relevance"],
        "low_relevance_count": low,
        "medium_relevance_count": medium,
        "high_relevance_count": high,
    }


# ---------------------------------------------------------------------
# Part 7 — additional training need (overall + by course)
# ---------------------------------------------------------------------


def get_additional_training_overview(db: Session) -> dict:
    updates = _followup_update_rows(db)
    total = len(updates)
    needed = sum(1 for u in updates if u.additional_training_needed is True)
    return {
        "total_responses": total,
        "additional_training_needed_count": needed,
        "additional_training_percentage": _pct(needed, total),
    }


def get_additional_training_by_course(db: Session) -> list:
    # Same grouped data as skill-gaps-by-course; just a different view of it.
    return get_skill_gaps_by_course(db)


# ---------------------------------------------------------------------
# Part 8 — longitudinal outcome insight
# ---------------------------------------------------------------------


def get_longitudinal_outcomes(db: Session) -> dict:
    training_completed = (
        db.query(TrainingRecord).filter(TrainingRecord.status == "Completed").count()
    )
    # One grouped query instead of one count per follow-up type
    completed_by_type = dict(
        db.query(FollowUp.followup_type, func.count(FollowUp.id))
        .filter(FollowUp.status == "Completed")
        .group_by(FollowUp.followup_type)
        .all()
    )
    followup_counts = {ftype: completed_by_type.get(ftype, 0) for ftype in FOLLOWUP_TYPES}
    retention = analytics_service.get_retention_rate(db)
    employed_trainees = retention["employed_trainees"]

    return {
        "training_completed": training_completed,
        "30_day_followups_completed": followup_counts["30_DAY"],
        "90_day_followups_completed": followup_counts["90_DAY"],
        "6_month_followups_completed": followup_counts["6_MONTH"],
        "12_month_followups_completed": followup_counts["12_MONTH"],
        "employed_trainees": employed_trainees,
        "retained_trainees": retention["retained_trainees"],
    }


# ---------------------------------------------------------------------
# Part 9 — programme improvement observations (soft, worded language)
# ---------------------------------------------------------------------


def generate_programme_observations(db: Session) -> list:
    observations = []

    skill_gaps = get_skill_gaps_overview(db)
    if skill_gaps["total_followups"] > 0 and skill_gaps["skill_gap_percentage"] >= 25:
        observations.append(
            {
                "area": "Skill Gap",
                "observation": (
                    f"{skill_gaps['skill_gap_percentage']}% of recorded follow-ups "
                    "reported a skill gap, which may indicate a need to review "
                    "course content or provide additional training."
                ),
            }
        )

    relevance = analytics_service.get_training_relevance(db)
    if relevance["total_responses"] > 0 and relevance["average_relevance"] < 3:
        observations.append(
            {
                "area": "Training Relevance",
                "observation": (
                    f"Average reported training relevance is "
                    f"{relevance['average_relevance']}/5, which indicates course "
                    "relevance may need review."
                ),
            }
        )

    for reason in analytics_service.get_non_placement_reasons(db):
        if reason["reason"] == "Location Problem" and reason["percentage"] >= 20:
            observations.append(
                {
                    "area": "Non-Placement — Location",
                    "observation": (
                        f"Location-related barriers are reported in "
                        f"{reason['percentage']}% of recorded non-placement cases."
                    ),
                }
            )

    attrition = analytics_service.get_attrition(db)
    if attrition["total_employment_records"] > 0 and attrition["attrition_rate"] >= 20:
        observations.append(
            {
                "area": "Attrition",
                "observation": (
                    f"{attrition['attrition_rate']}% of employment records are "
                    "associated with a trainee later leaving or being terminated, "
                    "which may suggest a need for stronger post-placement support."
                ),
            }
        )

    return observations


def get_programme_improvement(db: Session) -> dict:
    placement = analytics_service.get_placement_rate(db)
    employment = analytics_service.get_employment_rate(db)
    retention = analytics_service.get_retention_rate(db)
    skill_gaps = get_skill_gaps_overview(db)
    relevance = analytics_service.get_training_relevance(db)
    non_placement = analytics_service.get_non_placement_reasons(db)
    attrition = analytics_service.get_attrition(db)
    wages = analytics_service.get_wage_progression(db)

    return {
        "metrics": {
            "placement_rate": placement["placement_rate"],
            "employment_rate": employment["employment_rate"],
            "retention_rate": retention["retention_rate"],
            "skill_gap_percentage": skill_gaps["skill_gap_percentage"],
            "additional_training_percentage": skill_gaps["additional_training_percentage"],
            "average_training_relevance": relevance["average_relevance"],
            "attrition_rate": attrition["attrition_rate"],
            "average_salary_growth_percentage": wages["average_salary_growth_percentage"],
        },
        "non_placement_reasons": non_placement,
        "observations": generate_programme_observations(db),
    }


# ---------------------------------------------------------------------
# Part 10 — remedial action data (structured area/metric/action)
# ---------------------------------------------------------------------


def get_remedial_actions(db: Session) -> list:
    actions = []

    skill_gaps = get_skill_gaps_overview(db)
    if skill_gaps["total_followups"] > 0 and skill_gaps["skill_gap_percentage"] >= 25:
        actions.append(
            {
                "area": "Skill Development",
                "metric": {"skill_gap_percentage": skill_gaps["skill_gap_percentage"]},
                "action": "Review course skill coverage and consider additional skill training.",
            }
        )

    relevance = analytics_service.get_training_relevance(db)
    if relevance["total_responses"] > 0 and relevance["average_relevance"] < 3:
        actions.append(
            {
                "area": "Training Relevance",
                "metric": {"average_training_relevance": relevance["average_relevance"]},
                "action": "Review course content against current job requirements.",
            }
        )

    for reason in analytics_service.get_non_placement_reasons(db):
        if reason["reason"] == "Location Problem" and reason["percentage"] >= 20:
            actions.append(
                {
                    "area": "Location",
                    "metric": {"location_problem_percentage": reason["percentage"]},
                    "action": "Consider location-accessible placement opportunities or mobility support.",
                }
            )

    retention = analytics_service.get_retention_rate(db)
    if retention["employed_trainees"] > 0 and retention["retention_rate"] < 70:
        actions.append(
            {
                "area": "Job Retention",
                "metric": {"retention_rate": retention["retention_rate"]},
                "action": "Review post-placement support and follow-up frequency.",
            }
        )

    return actions


# ---------------------------------------------------------------------
# Part 11 — resource allocation (extends Phase 6's version with completed_count)
# ---------------------------------------------------------------------


def get_resource_allocation(db: Session) -> list:
    base = {row["district"]: row for row in analytics_service.get_resource_allocation(db)}
    district_outcomes = {row["district"]: row for row in analytics_service.get_district_outcomes(db)}

    result = []
    for district, row in sorted(base.items()):
        completed_count = district_outcomes.get(district, {}).get("completed", 0)
        result.append(
            {
                "district": district,
                "trainee_count": row["trainee_count"],
                "completed_count": completed_count,
                "unemployed_count": row["unemployed_count"],
                "skill_gap_count": row["skill_gap_count"],
                "additional_training_count": row["additional_training_needed"],
                "non_placement_count": row["non_placement_count"],
                "attrition_count": row["attrition_count"],
            }
        )
    return result


# ---------------------------------------------------------------------
# Part 12 — provider/course accountability (measurement, not ranking)
# ---------------------------------------------------------------------


def _employment_rows_with_group(db: Session):
    """Every employment record (id + status) with its training's course_name / provider_name."""
    return _cached(
        db,
        "employment_rows_with_group",
        lambda: db.query(
            EmploymentRecord.id,
            EmploymentRecord.employment_status,
            TrainingRecord.course_name,
            TrainingRecord.provider_name,
        )
        .join(Outcome, EmploymentRecord.outcome_pk_id == Outcome.id)
        .join(TrainingRecord, Outcome.training_record_pk_id == TrainingRecord.id)
        .all(),
    )


def _group_employment_stats(db: Session, rows, key_is_course: bool) -> dict:
    latest_rows = _latest_employment_status_rows(db)
    wage_by_employment = _wages_by_employment(db)

    groups = defaultdict(lambda: {"total": 0, "active": 0, "attrition": 0, "growth": []})
    for emp in rows:
        key = emp.course_name if key_is_course else emp.provider_name
        bucket = groups[key]
        bucket["total"] += 1
        status = _resolve_latest_status(emp, latest_rows)
        if status == "Active":
            bucket["active"] += 1
        if status in ATTRITION_STATUSES:
            bucket["attrition"] += 1
        progression = wage_progression_for(wage_by_employment.get(emp.id, []))
        if progression is not None:
            bucket["growth"].append(progression["growth_percentage"])

    result = {}
    for key, bucket in groups.items():
        result[key] = {
            "retention_rate": _pct(bucket["active"], bucket["total"]),
            "attrition_rate": _pct(bucket["attrition"], bucket["total"]),
            "average_salary_growth_percentage": _avg(bucket["growth"]),
        }
    return result


def _accountability_for(db: Session, base_rows: list, name_field: str, key_is_course: bool) -> list:
    followup_groups = _group_followup_stats(_followup_update_rows_with_group(db), key_is_course)
    employment_groups = _group_employment_stats(db, _employment_rows_with_group(db), key_is_course)

    result = []
    for row in base_rows:
        name = row[name_field]
        followup_stats = followup_groups.get(name, {})
        employment_stats = employment_groups.get(name, {})
        result.append(
            {
                "name": name,
                "total_trainees": row["total_trainees"],
                "completion_rate": _pct(row["completed"], row["total_trainees"]),
                "placement_rate": row["placement_rate"],
                "employment_rate": _pct(row["employed"], row["completed"]),
                # Groups with no employment / follow-up data get 0 rates
                # (with no records behind them) and null averages.
                "retention_rate": employment_stats.get("retention_rate", 0.0),
                "average_training_relevance": followup_stats.get("average_training_relevance"),
                "skill_gap_percentage": followup_stats.get("skill_gap_percentage", 0.0),
                "attrition_rate": employment_stats.get("attrition_rate", 0.0),
                "average_salary_growth_percentage": employment_stats.get(
                    "average_salary_growth_percentage"
                ),
            }
        )
    return result


def get_accountability(db: Session) -> dict:
    courses = _accountability_for(
        db, analytics_service.get_course_performance(db), "course_name", key_is_course=True
    )
    providers = _accountability_for(
        db, analytics_service.get_provider_performance(db), "provider_name", key_is_course=False
    )
    return {"courses": courses, "providers": providers}


# ---------------------------------------------------------------------
# Part 13 — data quality
# ---------------------------------------------------------------------


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def get_data_quality(db: Session) -> dict:
    trainees = db.query(
        Trainee.id,
        Trainee.trainee_id,
        Trainee.full_name,
        Trainee.phone,
        Trainee.current_location,
        Trainee.gender,
        Trainee.dob,
    ).all()
    trainings = [tr for tr, _outcome, _trainee in _all_training_rows(db)]
    employments = _employment_rows(db)

    trainees_missing_phone = sum(1 for t in trainees if _blank(t.phone))
    trainees_missing_location = sum(1 for t in trainees if _blank(t.current_location))
    trainees_missing_gender = sum(1 for t in trainees if _blank(t.gender))
    trainees_missing_dob = sum(1 for t in trainees if t.dob is None)

    completed_trainings = [t for t in trainings if t.status == "Completed"]
    training_missing_completion_date = sum(1 for t in completed_trainings if t.end_date is None)
    training_missing_attendance = sum(1 for t in trainings if t.attendance_percentage is None)
    training_missing_assessment = sum(1 for t in trainings if t.assessment_score is None)

    employment_missing_salary = sum(1 for e in employments if e.salary is None)
    employment_missing_joining_date = sum(1 for e in employments if e.joining_date is None)

    # Longitudinal gaps: records that exist but whose follow-on evidence doesn't yet.
    # Wage / status / outcome sets come from loaders the other figures already use.
    with_wage = set(_wages_by_employment(db))
    with_verification = {
        pk for (pk,) in db.query(EmployerVerification.employment_pk_id).distinct()
    }
    with_status = set(_latest_employment_status_rows(db))
    with_outcome = set(_latest_outcome_by_training(db))

    # Counted outside the consent scope on purpose: it reports how many
    # trainees the other figures EXCLUDE (a count only, no identities).
    consent_withdrawn = (
        db.query(Trainee)
        .execution_options(skip_consent_scope=True)
        .filter(Trainee.consent_given.is_(False))
        .count()
    )
    # Reuses the trainee rows loaded above instead of reading the table again
    duplicate_trainees = sum(
        len(g["trainee_ids"]) for g in identity_service.group_duplicates(trainees)
    )

    # Follow-ups are only counted, so count them in the database
    followups_by_status = dict(
        db.query(FollowUp.status, func.count(FollowUp.id)).group_by(FollowUp.status).all()
    )
    total_followups = sum(followups_by_status.values())
    completed_followups = followups_by_status.get("Completed", 0)
    followups_not_completed = total_followups - completed_followups
    followups_not_reachable = followups_by_status.get("Not Reachable", 0)

    return {
        "trainees_missing_phone": trainees_missing_phone,
        "trainees_missing_location": trainees_missing_location,
        "trainees_missing_gender": trainees_missing_gender,
        "trainees_missing_dob": trainees_missing_dob,
        "training_missing_completion_date": training_missing_completion_date,
        "training_missing_attendance": training_missing_attendance,
        "training_missing_assessment": training_missing_assessment,
        "employment_missing_salary": employment_missing_salary,
        "employment_missing_joining_date": employment_missing_joining_date,
        "completed_training_without_outcome": sum(
            1 for t in completed_trainings if t.id not in with_outcome
        ),
        "employment_without_wage_history": sum(1 for e in employments if e.id not in with_wage),
        "employment_without_verification": sum(
            1 for e in employments if e.id not in with_verification
        ),
        "employment_without_status_history": sum(
            1 for e in employments if e.id not in with_status
        ),
        "trainees_consent_withdrawn_excluded": consent_withdrawn,
        "possible_duplicate_trainees": duplicate_trainees,
        "followups_not_completed": followups_not_completed,
        "followups_not_reachable": followups_not_reachable,
        "followup_completion_rate": _pct(completed_followups, total_followups),
    }


# ---------------------------------------------------------------------
# Part 14 — insight summary
# ---------------------------------------------------------------------


def get_insight_summary(db: Session) -> dict:
    placement = analytics_service.get_placement_rate(db)
    employment = analytics_service.get_employment_rate(db)
    retention = analytics_service.get_retention_rate(db)
    wages = analytics_service.get_wage_progression(db)
    skill_gaps = get_skill_gaps_overview(db)
    relevance = analytics_service.get_training_relevance(db)
    attrition = analytics_service.get_attrition(db)
    non_placement = analytics_service.get_non_placement_reasons(db)
    data_quality = get_data_quality(db)

    top_reason = non_placement[0]["reason"] if non_placement else None

    return {
        "metrics": {
            "placement_rate": placement["placement_rate"],
            "employment_rate": employment["employment_rate"],
            "retention_rate": retention["retention_rate"],
            "average_salary_growth_percentage": wages["average_salary_growth_percentage"],
            "skill_gap_percentage": skill_gaps["skill_gap_percentage"],
            "additional_training_percentage": skill_gaps["additional_training_percentage"],
            "average_training_relevance": relevance["average_relevance"],
            "attrition_rate": attrition["attrition_rate"],
            "top_non_placement_reason": top_reason,
            "followup_completion_rate": data_quality["followup_completion_rate"],
        },
        "insights": generate_programme_observations(db),
    }
