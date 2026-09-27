"""
Public impact summary (GET /api/public/impact-summary): no login, only
aggregates, small groups suppressed, consent respected.

Each test gets its own empty in-memory database (the isolated_db fixture in conftest.py).
"""

import pytest

from routes.analytics import clear_public_cache
from tests.test_phase8_hardening import admin, anon, make_outcome, make_trainee, make_training

PATH = "/api/public/impact-summary"


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_public_cache()
    yield
    clear_public_cache()


def _placed(district: str, outcome: str = "Employed", **trainee) -> str:
    trainee_id = make_trainee(district=district, **trainee)
    make_outcome(trainee_id, make_training(trainee_id), outcome)
    return trainee_id


def test_no_login_needed_and_read_only(isolated_db):
    res = anon.get(PATH)
    assert res.status_code == 200, res.text
    assert res.headers["cache-control"].startswith("public")
    assert anon.post(PATH).status_code == 405
    assert anon.delete(PATH).status_code == 405


def test_empty_database_gives_zeros_not_errors(isolated_db):
    body = anon.get(PATH).json()
    assert body["trainees_registered"] == 0
    assert body["placement_rate"] is None  # no population to rate
    assert body["districts"] == [] and body["other_districts"] is None


def test_contains_no_personal_data(isolated_db):
    _placed("Pune", full_name="Asha Unique-Name", phone="9812345678")
    for _ in range(5):
        _placed("Pune", full_name="Asha Unique-Name")
    text = anon.get(PATH).text
    for leak in ("Asha", "Unique-Name", "9812345678", "TRN", "Electrician", "ITI Pune", "Hadapsar"):
        assert leak not in text, leak


def test_small_groups_are_suppressed_and_pooled(isolated_db):
    for _ in range(6):
        _placed("Pune")
    for district in ("Satara", "Wardha", "Akola"):  # 2 + 2 + 2 completions, each too small
        _placed(district)
        _placed(district, outcome="Unemployed")
    _placed("Pune", outcome="Apprenticeship")  # a single apprentice

    body = anon.get(PATH).json()
    assert body["trainees_registered"] == 13
    assert body["trainings_completed"] == 13
    assert body["placement_rate"] == pytest.approx(10 / 13 * 100, abs=0.01)
    assert body["outcome_mix"]["employed"] == 9
    assert body["outcome_mix"]["apprenticeship"] is None  # 1 is too few to publish
    assert body["outcome_mix"]["self_employed"] == 0
    assert body["districts_covered"] == 4

    assert [d["district"] for d in body["districts"]] == ["Pune"]
    assert body["districts"][0]["completed_trainings"] == 7
    other = body["other_districts"]
    assert (other["districts"], other["completed_trainings"], other["placed_trainees"]) == (3, 6, 3)
    assert "Satara" not in anon.get(PATH).text


def test_trainees_without_consent_are_excluded(isolated_db):
    for _ in range(5):
        _placed("Pune")
    withdrawn = _placed("Pune")
    assert admin.post(f"/api/trainees/{withdrawn}/consent", json={"consent_given": False}).status_code == 200
    clear_public_cache()

    body = anon.get(PATH).json()
    assert body["trainees_registered"] == 5
    assert body["trainings_completed"] == 5


def test_result_is_cached_between_requests(isolated_db):
    assert anon.get(PATH).json()["trainees_registered"] == 0
    for _ in range(5):
        _placed("Pune")
    assert anon.get(PATH).json()["trainees_registered"] == 0  # still the cached figure
    clear_public_cache()
    assert anon.get(PATH).json()["trainees_registered"] == 5
