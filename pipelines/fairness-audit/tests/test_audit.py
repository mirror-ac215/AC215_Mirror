"""M3-02 checks without FairFace or the model: labels, gate, group numbers, gaps, report."""

import csv
import json
import re
from pathlib import Path

import pytest
import yaml

from mirror_fairness_audit import LABELS
from mirror_fairness_audit.audit import Row, audit, gaps, photo_gate, read_predictions, wilson
from mirror_fairness_audit.cli import main
from mirror_fairness_audit.fairface import read_labels
from mirror_fairness_audit.report import headline, markdown
from mirror_fairness_audit.score import FIELDS

ROOT = Path(__file__).parents[1]
PARAMS = yaml.safe_load((ROOT / "params.yaml").read_text())
GATEWAY_CONFIG = ROOT.parents[1] / "services/api-gateway/app/config.py"


def probs(top: str, p: float) -> dict[str, float]:
    """`top` gets p, the rest share 1 - p equally."""
    rest = (1 - p) / (len(LABELS) - 1)
    return {label: p if label == top else rest for label in LABELS}


def row(race="White", gender="Female", age="20-29", face=True, top="neutral", p=0.8) -> Row:
    return Row(race, gender, age, face, probs(top, p))


def params(**groups) -> dict:
    return {**PARAMS, "groups": {**PARAMS["groups"], **groups}}


def test_labels_are_read_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("file,age,gender,race,service_test\nval/1.jpg,20-29,Male,East Asian,False\n")
    assert read_labels(path)[0].race == "East Asian"
    path.write_text("file,age,gender,race\nval/1.jpg,20-29,Male,Asian\n")
    with pytest.raises(ValueError, match="unknown race 'Asian'"):
        read_labels(path)
    path.write_text("file,age,gender\nval/1.jpg,20-29,Male\n")
    with pytest.raises(ValueError, match="missing columns"):
        read_labels(path)


def test_gate_thresholds_match_the_gateway() -> None:
    """params.yaml must gate photos exactly like the gateway gates webcam windows."""
    source = GATEWAY_CONFIG.read_text()
    for name in ("min_top_prob", "min_margin"):
        match = re.search(rf"gate_{name}: float = Field\(default=([0-9.]+)", source)
        assert match, f"gate_{name} not found in {GATEWAY_CONFIG}"
        assert PARAMS["gate"][name] == float(match.group(1))


@pytest.mark.parametrize(
    ("top_p", "second_p", "passes"),
    [(0.50, 0.40, True), (0.44, 0.10, False), (0.46, 0.43, False), (0.46, 0.40, True)],
)
def test_photo_gate_needs_a_strong_clear_top(top_p: float, second_p: float, passes: bool) -> None:
    rest = (1 - top_p - second_p) / 5
    p = {label: rest for label in LABELS} | {"happy": top_p, "neutral": second_p}
    assert photo_gate(Row("White", "Male", "20-29", True, p), 0.45, 0.05) is passes


def test_wilson_interval_stays_in_range() -> None:
    low, high = wilson(0, 10)
    assert low == 0 and 0 < high < 0.35
    low, high = wilson(50, 100)
    assert low < 0.5 < high


def test_the_largest_gap_is_found_and_named() -> None:
    rows = [row(race="White") for _ in range(200)] + [
        row(race="Black", face=i % 2 == 0) for i in range(200)
    ]
    result = audit(rows, params(min_group_size=100))
    gap = result["largest_gap"]
    assert (gap["metric"], gap["attribute"]) == ("face_found", "race")
    assert (gap["high_group"], gap["low_group"]) == ("White", "Black")
    assert gap["gap"] == pytest.approx(0.5)
    assert gap["separated"]
    text = headline(result)
    assert "White 100.0% vs Black 50.0%" in text and "50.0 points" in text


def test_small_groups_are_listed_but_never_the_largest_gap() -> None:
    rows = [row(race="White") for _ in range(200)] + [
        row(race="Indian", face=False) for _ in range(5)
    ]
    result = audit(rows, params(min_group_size=100))
    assert result["attributes"]["race"]["groups"]["Indian"]["n"] == 5
    assert result["attributes"]["race"]["gaps"] == []


def test_negative_share_and_gate_are_per_group() -> None:
    rows = [row(gender="Female", top="sad") for _ in range(100)] + [
        row(gender="Male", top="happy", p=0.3) for _ in range(100)
    ]
    groups = audit(rows, params(min_group_size=50))["attributes"]["gender"]["groups"]
    assert groups["Female"]["metrics"]["share_negative"]["value"] == 1.0
    assert groups["Male"]["metrics"]["share_negative"]["value"] == 0.0
    assert groups["Male"]["metrics"]["gate_ok"]["value"] == 0.0  # 0.3 < 0.45


def test_gate_ok_needs_a_face() -> None:
    result = audit([row(face=False) for _ in range(10)], params(min_group_size=1))
    metrics = result["overall"]["metrics"]
    assert metrics["gate_ok"]["value"] == 0.0
    assert metrics["confidence"]["value"] == pytest.approx(0.8)  # the photo is still scored


def test_children_are_reported_separately() -> None:
    rows = [row(age="20-29") for _ in range(10)] + [row(age="3-9") for _ in range(4)]
    result = audit(rows, params(min_group_size=1))
    assert result["photos_in_scope"] == 10
    assert set(result["attributes"]["age"]["groups"]) == {"20-29"}
    assert result["excluded_ages"]["3-9"]["n"] == 4


def test_gap_within_noise_is_said_plainly() -> None:
    groups = {
        g: {"n": 100, "metrics": {"m": {"value": v, "low": v - 0.1, "high": v + 0.1}}}
        for g, v in (("A", 0.50), ("B", 0.45))
    }
    assert gaps(groups, 100)[0]["separated"] is False


def write_predictions(path: Path, rows: list[Row]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for i, r in enumerate(rows):
            writer.writerow(
                {
                    "file": f"val/{i}.jpg",
                    "race": r.race,
                    "gender": r.gender,
                    "age": r.age,
                    "face_found": r.face_found,
                    **r.probs,
                }
            )
    return path


def test_report_command_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    rows = [row(race="White") for _ in range(120)] + [
        row(race="Black", face=False) for _ in range(120)
    ]
    predictions = write_predictions(tmp_path / "predictions.csv", rows)
    assert read_predictions(predictions)[0] == rows[0]
    out = tmp_path / "report"
    assert (
        main(
            [
                "--params",
                str(ROOT / "params.yaml"),
                "report",
                "--predictions",
                str(predictions),
                "--output-dir",
                str(out),
            ]
        )
        == 0
    )
    assert "Largest gap" in capsys.readouterr().out
    payload = json.loads((out / "report.json").read_text())
    assert payload["largest_gap"]["metric"] in {"face_found", "gate_ok"}
    text = (out / "report.md").read_text()
    assert payload["headline"] in text
    assert "→" not in text


def test_report_refuses_predictions_from_another_model(tmp_path: Path) -> None:
    predictions = write_predictions(tmp_path / "predictions.csv", [row()])
    predictions.with_suffix(".meta.json").write_text(json.dumps({"model_version": "cv-vit-b16-v3"}))
    with pytest.raises(ValueError, match="cv-vit-b16-v3"):
        main(
            [
                "--params",
                str(ROOT / "params.yaml"),
                "report",
                "--predictions",
                str(predictions),
                "--output-dir",
                str(tmp_path / "r"),
            ]
        )


def test_markdown_states_the_limits() -> None:
    result = audit([row() for _ in range(3)], params(min_group_size=1))
    text = markdown(result, PARAMS, {})
    assert "not how accurate" in text and "No gap could be measured" in text
