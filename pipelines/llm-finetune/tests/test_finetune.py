"""M3-09 checks that run without a GPU: params, data formatting, the Vertex job spec."""

import csv
import json
from pathlib import Path

import pytest

from mirror_llm_finetune.cli import main
from mirror_llm_finetune.config import check, gcs_to_fuse, load_params, problems
from mirror_llm_finetune.data import fingerprint, read_split, to_example
from mirror_llm_finetune.train import adapter_metadata
from mirror_llm_finetune.vertex import job_spec

PARAMS_FILE = Path(__file__).parents[1] / "params.yaml"
PIN = "a" * 40


@pytest.fixture
def params() -> dict:
    p = load_params(PARAMS_FILE)
    p["base_model"]["revision"] = PIN
    p["vertex"]["image_uri"] = "us-docker.pkg.dev/proj/repo/llm-finetune:abc123"
    return p


def write_splits(folder: Path, rows: int = 2) -> Path:
    for split in ("train", "val", "test"):
        with (folder / f"{split}.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["pair_id", "prompt", "response"])
            writer.writeheader()
            for i in range(rows):
                writer.writerow({"pair_id": f"{split}{i}", "prompt": f"q{i}", "response": f"a{i}"})
    return folder


def test_committed_params_are_valid_apart_from_the_pin() -> None:
    raw = load_params(PARAMS_FILE)
    assert problems(raw, for_training=False) == []
    assert raw["output"]["adapter_name"] != "adapter-v1"  # never overwrite the inherited adapter


@pytest.mark.parametrize("revision", ["", "main", "abc123"])
def test_training_refuses_an_unpinned_base_model(params: dict, revision: str) -> None:
    params["base_model"]["revision"] = revision
    with pytest.raises(ValueError, match="40-character"):
        check(params, for_training=True)


def test_example_is_prompt_completion_chat(params: dict) -> None:
    example = to_example({"prompt": "How do I start?", "response": "One step."}, "SYSTEM")
    assert [m["role"] for m in example["prompt"]] == ["system", "user"]
    assert example["completion"] == [{"role": "assistant", "content": "One step."}]


def test_system_prompt_names_no_real_person(params: dict) -> None:
    assert "peterson" not in params["system_prompt"].lower()
    assert "not a doctor" in params["system_prompt"]


def test_missing_column_and_empty_split_fail_loudly(tmp_path: Path) -> None:
    (tmp_path / "train.csv").write_text("prompt,answer\nq,a\n")
    with pytest.raises(ValueError, match="response"):
        read_split(tmp_path, "train")
    (tmp_path / "val.csv").write_text("pair_id,prompt,response\n")
    with pytest.raises(ValueError, match="no rows"):
        read_split(tmp_path, "val")


def test_fingerprint_changes_when_the_data_changes(tmp_path: Path) -> None:
    write_splits(tmp_path)
    before = fingerprint(tmp_path)
    assert fingerprint(tmp_path) == before
    with (tmp_path / "test.csv").open("a") as handle:
        handle.write("x,new,row\n")
    assert fingerprint(tmp_path) != before


def test_metadata_records_what_the_adapter_came_from(params: dict) -> None:
    meta = adapter_metadata(params, "f" * 64, "https://wandb.ai/run")
    assert meta["base_revision"] == PIN
    assert meta["data_version"] == "persona/v1" and meta["data_sha256"] == "f" * 64
    assert meta["lora"]["r"] == 32


def test_gcs_paths_map_to_the_fuse_mount() -> None:
    assert gcs_to_fuse("gs://bucket/data/v1") == "/gcs/bucket/data/v1"
    assert gcs_to_fuse("data/local") == "data/local"


def test_job_spec_one_gpu_replica_reading_through_fuse(params: dict) -> None:
    spec = job_spec(params, "gs://mirror-ac215-data/data/persona/v1", {"WANDB_API_KEY": "k"})
    pool = spec["worker_pool_specs"][0]
    assert pool["replica_count"] == 1
    assert pool["machine_spec"]["accelerator_type"] == "NVIDIA_L4"
    args = pool["container_spec"]["args"]
    assert args == ["train", "--data-dir", "/gcs/mirror-ac215-data/data/persona/v1", "--upload"]


def test_job_spec_needs_an_image_and_a_gcs_data_path(params: dict) -> None:
    with pytest.raises(ValueError, match="gs://"):
        job_spec(params, "data/local", {})
    params["vertex"]["image_uri"] = ""
    with pytest.raises(ValueError, match="image_uri"):
        job_spec(params, "gs://b/d", {})


def test_dry_run_prints_the_spec_without_secrets(
    params: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import yaml

    path = tmp_path / "params.yaml"
    path.write_text(yaml.safe_dump(params))
    monkeypatch.setenv("WANDB_API_KEY", "secret-key")
    assert main(["--params", str(path), "submit", "--data-uri", "gs://b/d", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "secret-key" not in out
    assert json.loads(out)["display_name"] == "mirror-llm-finetune-adapter-v2"
