"""Smoothing and gating (M3-04): one synthetic frame sequence per status.

No camera or cv-service needed: each test builds fake cv-service readings
and checks what gate() makes of them. Every output is also checked against
the real context-object contract, so the gateway can never send a shape the
llm-service side doesn't expect.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.config import Settings
from app.gating import FrameReading, FrameWindow, gate

SCHEMA = json.loads(
    (Path(__file__).parents[3] / "docs" / "contracts" / "context_object.schema.json").read_text(
        encoding="utf-8"
    )
)
# Just the `visual` part of the contract (it reuses the shared top2 definition).
VISUAL_VALIDATOR = Draft202012Validator({"$defs": SCHEMA["$defs"], **SCHEMA["properties"]["visual"]})

LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")


def probs(**overrides: float) -> dict[str, float]:
    """7 probabilities: the named ones as given, the rest share what is left."""
    rest = (1.0 - sum(overrides.values())) / (len(LABELS) - len(overrides))
    return {label: overrides.get(label, rest) for label in LABELS}


def face(ts: float, **overrides: float) -> FrameReading:
    return FrameReading(ts=ts, face_found=True, probs=probs(**overrides))


def no_face(ts: float) -> FrameReading:
    return FrameReading(ts=ts, face_found=False, probs={})


@pytest.fixture
def settings() -> Settings:
    return Settings()


def check(result: dict) -> dict:
    VISUAL_VALIDATOR.validate(result)  # raises if the shape breaks the contract
    return result


def test_camera_off_when_no_consent(settings: Settings) -> None:
    result = check(gate([face(0, sad=0.9)], settings, camera_on=False))
    assert result == {"status": "camera_off"}


def test_ok_when_steady_and_confident(settings: Settings) -> None:
    readings = [face(t, sad=0.6, neutral=0.25) for t in range(5)]
    result = check(gate(readings, settings, camera_on=True))
    assert result["status"] == "ok"
    assert result["top2"][0] == ["sad", 0.6]
    assert result["stability"] == 1.0
    assert result["n_frames"] == 5


def test_smoothing_ignores_one_odd_frame(settings: Settings) -> None:
    # Four sad frames and one surprised blink: the average still says sad.
    readings = [face(t, sad=0.6, neutral=0.25) for t in range(4)] + [face(4, surprise=0.9)]
    result = check(gate(readings, settings, camera_on=True))
    assert result["status"] == "ok"
    assert result["top2"][0][0] == "sad"
    assert result["stability"] == 0.8


def test_uncertain_when_top_two_are_close(settings: Settings) -> None:
    # Strong enough (0.50 >= 0.45) but only 0.03 ahead of neutral (< 0.05).
    readings = [face(t, sad=0.50, neutral=0.47) for t in range(5)]
    assert check(gate(readings, settings, camera_on=True))["status"] == "uncertain"


def test_uncertain_when_reading_is_weak(settings: Settings) -> None:
    readings = [face(t, sad=0.30, neutral=0.15) for t in range(5)]
    assert check(gate(readings, settings, camera_on=True))["status"] == "uncertain"


def test_uncertain_when_most_frames_disagree_with_the_average(settings: Settings) -> None:
    # 2 frames clearly sad, 3 frames narrowly happy (happy 0.50, sad 0.45). Averaged, sad leads
    # comfortably (0.63 vs 0.31), but it is the top emotion in only 2 of 5 frames: stability 0.40 < 0.50.
    readings = [face(t, sad=0.9) for t in range(2)] + [face(t, happy=0.50, sad=0.45) for t in range(2, 5)]
    result = check(gate(readings, settings, camera_on=True))
    assert result["status"] == "uncertain"
    assert result["top2"][0][0] == "sad"
    assert result["stability"] == 0.4


def test_dropped_when_too_few_frames(settings: Settings) -> None:
    result = check(gate([face(0, sad=0.9), face(1, sad=0.9)], settings, camera_on=True))
    assert result["status"] == "dropped"
    assert "top2" not in result  # nothing to say about the face


def test_dropped_when_face_mostly_missing(settings: Settings) -> None:
    readings = [face(t, sad=0.9) for t in range(3)] + [no_face(t) for t in range(3, 10)]
    assert check(gate(readings, settings, camera_on=True))["status"] == "dropped"


def test_dropped_when_window_is_empty(settings: Settings) -> None:
    assert check(gate([], settings, camera_on=True))["status"] == "dropped"


def test_window_keeps_only_recent_and_bounded_readings() -> None:
    window = FrameWindow(max_frames=3)
    for t in range(5):
        window.add(face(t, sad=0.9))
    # Only the last 3 are kept (memory cap), and only those within 1.5 s count.
    assert [r.ts for r in window.recent(now=4, window_s=10)] == [2, 3, 4]
    assert [r.ts for r in window.recent(now=4, window_s=1.5)] == [3, 4]


def test_thresholds_come_from_config(monkeypatch) -> None:
    # A stricter setting turns the same steady reading from ok into uncertain.
    readings = [face(t, sad=0.6, neutral=0.25) for t in range(5)]
    monkeypatch.setenv("GATE_MIN_TOP_PROB", "0.7")
    assert gate(readings, Settings(), camera_on=True)["status"] == "uncertain"

# Owen (#52): a bad threshold or frame setting must stop the gateway at startup.
@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("GATE_MIN_TOP_PROB", "1.5"),
        ("GATE_MIN_MARGIN", "-0.1"),
        ("GATE_MIN_STABILITY", "2"),
        ("GATE_MIN_FACE_RATIO", "1.01"),
        ("GATE_MIN_FRAMES", "0"),
        ("GATE_MAX_FRAMES", "0"),
        ("GATE_WINDOW_S", "0"),
        ("GATE_MAX_FRAMES", "2"),  # smaller than GATE_MIN_FRAMES (3): could never be "ok"
    ],
)
def test_invalid_gate_settings_are_rejected(monkeypatch, variable: str, value: str) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        Settings()


# Owen (#52): a broken cv-service reply counts as "no face", so it ends in "dropped", never a crash.
@pytest.mark.parametrize(
    "bad_probs",
    [
        {"sad": 1.0},  # one label only (used to raise IndexError)
        {k: v for k, v in probs(sad=0.9).items() if k != "fear"},  # a label missing
        {**probs(sad=0.9), "contempt": 0.0},  # a label cv-service doesn't have
        probs(sad=float("nan")),
        probs(sad=1.5),
        {**probs(sad=0.9), "happy": "0.1"},
        {**probs(sad=0.9), "happy": True},
    ],
    ids=["one label", "missing label", "extra label", "NaN", "above 1", "text", "bool"],
)
def test_malformed_probabilities_are_dropped_not_crashed(settings: Settings, bad_probs: dict) -> None:
    readings = [FrameReading(ts=t, face_found=True, probs=bad_probs) for t in range(5)]
    assert check(gate(readings, settings, camera_on=True))["status"] == "dropped"


def test_one_malformed_frame_is_skipped_and_the_rest_still_count(settings: Settings) -> None:
    readings = [face(t, sad=0.6, neutral=0.25) for t in range(4)]
    readings.append(FrameReading(ts=4, face_found=True, probs={"sad": float("nan")}))
    result = check(gate(readings, settings, camera_on=True))
    assert result["status"] == "ok"  # 4 good frames of 5: enough faces (0.8 >= 0.5)
    assert result["top2"][0] == ["sad", 0.6]
    assert result["n_frames"] == 5
