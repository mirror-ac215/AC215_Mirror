"""Tests on a tiny fake release with the same file layout and line formats as IEMOCAP.

No real IEMOCAP data is used: the licence forbids redistribution, and CI has no access to it.
"""

import csv
import json
import tarfile
from pathlib import Path

import pytest
import yaml

from mirror_iemocap_data.pipeline import (
    build,
    describe,
    parse_evaluation,
    parse_transcription,
    run,
)

PARAMS = yaml.safe_load((Path(__file__).parents[1] / "params.yaml").read_text())

EVALUATION = """% [START_TIME - END_TIME] TURN_NAME EMOTION [V, A, D]

[1.0000 - 2.5000]\tSes01F_impro01_F000\tneu\t[2.5000, 2.0000, 2.5000]
C-E1:\tNeutral;\t()
A-E1:\tval 3; act 2; dom  3;\t()

[3.0000 - 4.2500]\tSes01F_impro01_M000\texc\t[4.0000, 3.5000, 3.0000]
C-E1:\tExcited;\t()

[5.0000 - 6.0000]\tSes01F_impro01_F001\tfru\t[2.0000, 3.5000, 3.0000]

[6.5000 - 7.0000]\tSes01F_impro01_M001\txxx\t[2.5000, 2.5000, 2.5000]

[7.5000 - 9.0000]\tSes01F_impro01_F002\tsad\t[1.5000, 2.0000, 2.0000]
"""

TRANSCRIPTION = """Ses01F_impro01_F000 [001.0000-002.5000]: Is this the right line?
Ses01F_impro01_M000 [003.0000-004.2500]: Oh, that is wonderful news!
Ses01F_impro01_F001 [005.0000-006.0000]: Nobody here is listening to me.
Ses01F_impro01_M001 [006.5000-007.0000]: Well.
Ses01F_impro01_F002 [007.5000-009.0000]:   I miss   how things were.
M: [BREATHING]
"""

SCRIPTED_EVALUATION = "[0.5000 - 1.5000]\tSes02M_script01_1_M000\tang\t[1.5000, 4.0000, 4.0000]\n"
SCRIPTED_TRANSCRIPTION = "Ses02M_script01_1_M000 [000.5000-001.5000]: Give it back now.\n"


def _release(root: Path) -> Path:
    """Write a fake IEMOCAP_full_release/ folder and return it."""
    release = root / "IEMOCAP_full_release"
    files = {
        "Session1/dialog/EmoEvaluation/Ses01F_impro01.txt": EVALUATION,
        "Session1/dialog/transcriptions/Ses01F_impro01.txt": TRANSCRIPTION,
        "Session2/dialog/EmoEvaluation/Ses02M_script01_1.txt": SCRIPTED_EVALUATION,
        "Session2/dialog/transcriptions/Ses02M_script01_1.txt": SCRIPTED_TRANSCRIPTION,
        "Session1/dialog/EmoEvaluation/._Ses01F_impro01.txt": "macOS metadata, not a label file",
        "Session1/dialog/EmoEvaluation/Categorical/Ses01F_impro01_e1_cat.txt": "per-rater file",
    }
    for name, text in files.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return release


def _archive(root: Path) -> Path:
    """Pack the fake release the way the real archive is packed: paths start with ./"""
    release = _release(root)
    archive = root / "IEMOCAP_full_release.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(release, arcname="./IEMOCAP_full_release")
    return archive


def test_consensus_lines_are_parsed_and_rater_lines_ignored():
    rows = parse_evaluation(EVALUATION)
    assert [r.utterance_id for r in rows] == [
        "Ses01F_impro01_F000", "Ses01F_impro01_M000", "Ses01F_impro01_F001",
        "Ses01F_impro01_M001", "Ses01F_impro01_F002",
    ]
    assert rows[0].code == "neu" and rows[0].start_s == 1.0 and rows[0].end_s == 2.5
    assert (rows[1].valence, rows[1].arousal, rows[1].dominance) == (4.0, 3.5, 3.0)


def test_transcripts_are_parsed_and_non_utterance_lines_skipped():
    texts = parse_transcription(TRANSCRIPTION)
    assert texts["Ses01F_impro01_F002"] == "I miss how things were."
    assert len(texts) == 5  # "M: [BREATHING]" has no utterance id


def test_utterance_id_is_described():
    assert describe("Ses01F_impro01_F000") == {
        "session": "1", "dialog": "Ses01F_impro01", "speaker": "F", "kind": "improvised"}
    assert describe("Ses02M_script01_1_M000") == {
        "session": "2", "dialog": "Ses02M_script01_1", "speaker": "M", "kind": "scripted"}


def test_labels_are_mapped_frustration_kept_unlabelled_and_xxx_dropped(tmp_path):
    rows, counts = build(_release(tmp_path), PARAMS["labels"], PARAMS["keep_unlabelled"])
    assert [(r["utterance_id"], r["iemocap_label"], r["label"]) for r in rows] == [
        ("Ses01F_impro01_F000", "neu", "neutral"),
        ("Ses01F_impro01_F001", "fru", ""),    # frustration: kept, no Mirror label
        ("Ses01F_impro01_F002", "sad", "sadness"),
        ("Ses01F_impro01_M000", "exc", "joy"),  # excited -> joy
        ("Ses02M_script01_1_M000", "ang", "anger"),
    ]
    assert counts["dropped"] == {"label:xxx": 1}
    assert counts["files_read"] == {"EmoEvaluation": 2, "transcriptions": 2}


@pytest.mark.parametrize(("code", "expected"), [
    ("neu", "neutral"), ("hap", "joy"), ("exc", "joy"), ("sad", "sadness"),
    ("ang", "anger"), ("fea", "fear"), ("dis", "disgust"), ("sur", "surprise"),
    ("fru", ""),          # kept without a Mirror label
    ("oth", None),        # dropped
    ("xxx", None),        # dropped
])
def test_every_iemocap_code_is_handled(tmp_path, code, expected):
    """All 11 IEMOCAP codes: 8 map to Mirror's 7 emotions, fru is kept unlabelled, 2 drop."""
    release = tmp_path / "IEMOCAP_full_release"
    for folder, text in [
        ("EmoEvaluation", f"[0.5000 - 1.5000]\tSes03F_impro01_F000\t{code}\t[2.0, 2.0, 2.0]\n"),
        ("transcriptions", "Ses03F_impro01_F000 [000.5000-001.5000]: A test line.\n"),
    ]:
        path = release / "Session3/dialog" / folder / "Ses03F_impro01.txt"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
    rows, counts = build(release, PARAMS["labels"], PARAMS["keep_unlabelled"])
    if expected is None:
        assert rows == [] and counts["dropped"] == {f"label:{code}": 1}
    else:
        assert [r["label"] for r in rows] == [expected]


def test_frustration_can_be_mapped_in_params(tmp_path):
    rows, _ = build(_release(tmp_path), {**PARAMS["labels"], "fru": "anger"})
    assert ("Ses01F_impro01_F001", "anger") in [(r["utterance_id"], r["label"]) for r in rows]


def test_frustration_is_dropped_when_not_kept(tmp_path):
    rows, counts = build(_release(tmp_path), PARAMS["labels"], keep_unlabelled=[])
    assert "fru" not in [r["iemocap_label"] for r in rows]
    assert counts["dropped"] == {"label:fru": 1, "label:xxx": 1}


def test_utterance_without_transcript_is_dropped(tmp_path):
    release = _release(tmp_path)
    transcript = release / "Session1/dialog/transcriptions/Ses01F_impro01.txt"
    transcript.write_text(TRANSCRIPTION.replace("Ses01F_impro01_F000 ", "XX "), encoding="utf-8")
    rows, counts = build(release, PARAMS["labels"])
    assert "Ses01F_impro01_F000" not in [r["utterance_id"] for r in rows]
    assert counts["dropped"]["no_transcript"] == 1


def test_archive_and_folder_give_identical_outputs(tmp_path):
    archive = _archive(tmp_path / "a")
    folder = _release(tmp_path / "b")
    report_a = run(archive, tmp_path / "out_a", PARAMS)
    report_b = run(folder, tmp_path / "out_b", PARAMS)
    assert report_a["utterances_sha256"] == report_b["utterances_sha256"]
    assert (tmp_path / "out_a/utterances.csv").read_bytes() == (
        tmp_path / "out_b/utterances.csv").read_bytes()


def test_run_twice_is_byte_identical_and_report_is_complete(tmp_path):
    release = _release(tmp_path)
    first = run(release, tmp_path / "one", PARAMS)
    second = run(release, tmp_path / "two", PARAMS)
    assert first == second
    report = json.loads((tmp_path / "one/report.json").read_text())
    assert report["utterances_kept"] == 5
    assert report["labels_kept"] == {"anger": 1, "joy": 1, "neutral": 1, "sadness": 1}
    assert report["kept_unlabelled"] == {"fru": 1}
    assert report["per_session"] == {"1": 4, "2": 1}
    with (tmp_path / "one/utterances.csv").open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[0] == "utterance_id" and header[-1] == "text"


def test_missing_source_and_wrong_folder_fail_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="dvc pull"):
        build(tmp_path / "nope.tar.gz", PARAMS["labels"])
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no EmoEvaluation labels"):
        build(tmp_path / "empty", PARAMS["labels"])
