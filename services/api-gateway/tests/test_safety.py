"""M3-07: deterministic safety check.

The curated set in safety_cases.yaml must pass 100%. CI runs this on every
change to services/api-gateway: a rule edit can't silently weaken it.
"""

import json
import logging
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app import chat, safety
from app.main import app

CASES = yaml.safe_load((Path(__file__).parent / "safety_cases.yaml").read_text())
PATIENT = {"Authorization": "Bearer dev-patient-token"}


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
def test_curated_case(case: dict) -> None:
    result = safety.check(case["text"])
    expected = None if case["expect"] == "none" else case["expect"]
    assert result.kind == expected, f"rule={result.rule_id}"


def test_curated_set_is_big_enough_and_covers_every_outcome() -> None:
    expects = [c["expect"] for c in CASES]
    assert len(CASES) >= 50
    assert {"crisis", "medical", "support", "none"} <= set(expects)


def test_every_rule_is_covered_by_a_case() -> None:
    fired = {safety.check(c["text"]).rule_id for c in CASES}
    rules = {rid for rid, _ in safety.CRISIS_RULES + safety.MEDICAL_RULES + safety.SUPPORT_RULES}
    assert rules - fired == set(), "add a case for each new rule"


def test_crisis_wins_over_medical() -> None:
    assert safety.check("how many pills should I take to overdose").kind == "crisis"


def test_payloads_match_the_contract() -> None:
    crisis = safety.crisis_payload(review_flag_created=True)
    assert set(crisis) == {"message", "resources", "review_flag_created"}
    assert any("988" in r["contact"] for r in crisis["resources"])
    assert set(safety.medical_payload()) == {"message"}


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


async def send(text: str) -> list[tuple[str, dict]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session = await c.post("/sessions", json={"camera_consent": False}, headers=PATIENT)
        sid = session.json()["session_id"]
        response = await c.post(f"/sessions/{sid}/messages", json={"text": text}, headers=PATIENT)
    assert response.status_code == 200
    return events(response.text)


@pytest.mark.anyio
async def test_crisis_turn_streams_only_crisis_and_creates_a_review_flag() -> None:
    before = len(chat.review_flags)
    stream = await send("I don't want to be alive anymore")

    assert [name for name, _ in stream] == ["crisis"]  # no persona reply
    assert stream[0][1]["review_flag_created"] is True
    assert len(chat.review_flags) == before + 1
    flag = chat.review_flags[-1]
    assert flag["rule_id"] == "not-alive"
    assert flag["urgency"] == "urgent"
    assert "text" not in flag  # the flag points at the message, it doesn't copy it


@pytest.mark.anyio
async def test_medical_turn_streams_only_medical_and_no_flag() -> None:
    before = len(chat.review_flags)
    stream = await send("can I take ibuprofen with my zoloft?")

    assert [name for name, _ in stream] == ["medical"]
    assert len(chat.review_flags) == before


@pytest.mark.anyio
async def test_support_turn_offers_a_person_then_keeps_talking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat.settings, "clinic_booking_url", "https://clinic.example.test/book")
    monkeypatch.setattr(chat.settings, "clinic_phone", "555-0100")
    before = len(chat.review_flags)
    stream = await send("I need to talk to a real person")

    names = [name for name, _ in stream]
    assert names[0] == "support" and "token" in names and names[-1] == "done"
    actions = {a["type"]: a for a in stream[0][1]["actions"]}
    assert actions["schedule"]["url"] == "https://clinic.example.test/book"
    assert actions["call"]["contact"] == "555-0100"
    assert actions["live"]["available"] is False
    assert len(chat.review_flags) == before + 1
    assert chat.review_flags[-1]["urgency"] == "routine"


def test_support_actions_only_show_what_the_clinic_configured() -> None:
    payload = safety.support_payload(booking_url="", phone="", live_available=False)
    assert [a["type"] for a in payload["actions"]] == ["live"]
    assert "988" in payload["message"]


@pytest.mark.anyio
async def test_normal_turn_still_gets_the_persona_reply() -> None:
    stream = await send("I had a rough day at work")
    names = [name for name, _ in stream]
    assert names[-1] == "done" and "token" in names


@pytest.mark.anyio
async def test_message_text_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "I want to kill myself because of my exam"
    # The "mirror" logger doesn't propagate to root; attach caplog's handler to it directly.
    mirror_logger = logging.getLogger("mirror")
    mirror_logger.addHandler(caplog.handler)
    try:
        await send(secret)
    finally:
        mirror_logger.removeHandler(caplog.handler)
    assert any("safety_hit kind=crisis" in r.getMessage() for r in caplog.records)
    assert all(secret not in r.getMessage() for r in caplog.records)
