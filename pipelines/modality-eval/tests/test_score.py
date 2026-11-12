import pytest

from mirror_modality_eval import MIN_TEXT_PROB
from mirror_modality_eval.score import (
    Row,
    beyond_noise,
    compare,
    frustration_reads,
    score_mode,
    wilson,
)


def row(label="joy", text="joy", tp=0.9, face="happy", status="ok"):
    return Row(label=label, text_label=text, text_prob=tp, face_label=face, face_status=status)


def test_wilson_bounds_and_empty():
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(50, 100)
    assert 0.39 < low < 0.41 and 0.59 < high < 0.61
    low, high = wilson(0, 10)
    assert low == 0.0 and 0 < high < 0.35


def test_face_counts_only_when_gate_passed():
    assert row(status="ok").face_reading() == "joy"
    assert row(status="uncertain").face_reading() is None
    assert row(status="camera_off").face_reading() is None


def test_face_labels_map_to_mirror_names():
    assert row(face="angry", label="anger").face_reading() == "anger"
    assert row(face="sad", label="sadness").face_reading() == "sadness"
    assert row(face="neutral", label="neutral").face_reading() == "neutral"


def test_text_needs_the_bar():
    assert row(tp=MIN_TEXT_PROB).text_reading() == "joy"
    assert row(tp=MIN_TEXT_PROB - 0.01).text_reading() is None


def test_combined_prefers_text_then_face():
    assert row(tp=0.9, text="anger", label="anger", face="happy").combined_reading() == "anger"
    assert row(tp=0.1, face="happy").combined_reading() == "joy"
    assert row(tp=0.1, status="uncertain").combined_reading() is None


def test_score_mode_counts_only_rows_with_a_reading():
    rows = [
        row(label="joy", text="joy", tp=0.9),
        row(label="anger", text="sadness", tp=0.9),  # text counts, wrong
        row(label="sadness", tp=0.1, status="uncertain"),  # neither counts
    ]
    s = score_mode(rows, "text")
    assert s["scored_rows"] == 3
    assert s["counted"] == 2
    assert s["accuracy"] == pytest.approx(0.5)
    assert s["coverage"] == pytest.approx(2 / 3)


def test_rare_and_unlabelled_rows_are_not_scored():
    rows = [row(label="fear", text="fear"), row(label="", text="neutral")]
    assert score_mode(rows, "text")["scored_rows"] == 0


def test_beyond_noise():
    a = {"low": 0.6, "high": 0.7}
    assert beyond_noise(a, {"low": 0.2, "high": 0.4})
    assert not beyond_noise(a, {"low": 0.5, "high": 0.65})


def test_compare_reports_all_modes():
    rows = [row(), row(label="anger", text="anger", face="angry")]
    result = compare(rows)
    assert set(result) >= {"face", "text", "both", "face_vs_text_beyond_noise"}


def test_frustration_is_reported_not_scored():
    rows = [row(label="", text="anger", tp=0.9, status="ok", face="angry"), row(label="joy")]
    f = frustration_reads(rows)
    assert f["rows"] == 1
    assert f["text"] == {"anger": 1}
    assert f["face"] == {"anger": 1}
