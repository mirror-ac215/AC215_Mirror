"""M3-09/M3-23 checks that run without a GPU: params, data, DVC freshness, secrets, job spec."""

import csv
import json
from pathlib import Path

import pytest

from mirror_llm_finetune import dvc_check
from mirror_llm_finetune.cli import main
from mirror_llm_finetune.config import check, gcs_to_fuse, load_params, problems
from mirror_llm_finetune.data import fingerprint, read_split, to_example
from mirror_llm_finetune.secret_manager import load_secrets, secret_refs
from mirror_llm_finetune.train import adapter_metadata, preflight
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


def repo_with_data(root: Path, params: dict) -> Path:
    """A repo checkout with the persona splits where params.yaml says DVC puts them."""
    data = root / params["data"]["dir"]
    data.mkdir(parents=True)
    return write_splits(data)


def dvc_reports(monkeypatch: pytest.MonkeyPatch, changes: dict) -> list:
    """Replace `dvc status` with a canned answer; returns the calls it saw."""
    calls: list = []

    def fake(root: Path, stage: str) -> dict:
        calls.append((root, stage))
        return changes

    monkeypatch.setattr(dvc_check, "dvc_changes", fake)
    return calls


def submit_argv(params: dict, tmp_path: Path) -> list[str]:
    import yaml

    path = tmp_path / "params.yaml"
    path.write_text(yaml.safe_dump(params))
    return [
        "--params",
        str(path),
        "submit",
        "--data-uri",
        "gs://b/d",
        "--repo-root",
        str(tmp_path),
    ]


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
    meta = adapter_metadata(params, "f" * 64, "b" * 40, "https://wandb.ai/run")
    assert meta["base_revision"] == PIN
    assert meta["git_sha"] == "b" * 40
    assert meta["data_version"] == "persona/v1" and meta["data_sha256"] == "f" * 64
    assert meta["lora"]["r"] == 32


def test_gcs_paths_map_to_the_fuse_mount() -> None:
    assert gcs_to_fuse("gs://bucket/data/v1") == "/gcs/bucket/data/v1"
    assert gcs_to_fuse("data/local") == "data/local"


def test_job_spec_one_gpu_replica_reading_through_fuse(params: dict) -> None:
    spec = job_spec(params, "gs://mirror-ac215-data/data/persona/v1", secret_refs(params))
    pool = spec["worker_pool_specs"][0]
    assert pool["replica_count"] == 1
    assert pool["machine_spec"]["accelerator_type"] == "NVIDIA_L4"
    args = pool["container_spec"]["args"]
    assert args == [
        "train",
        "--data-dir",
        "/gcs/mirror-ac215-data/data/persona/v1",
        "--upload",
    ]


def test_job_spec_needs_an_image_and_a_gcs_data_path(params: dict) -> None:
    with pytest.raises(ValueError, match="gs://"):
        job_spec(params, "data/local", {})
    params["vertex"]["image_uri"] = ""
    with pytest.raises(ValueError, match="image_uri"):
        job_spec(params, "gs://b/d", {})


def test_dry_run_spec_holds_secret_names_never_values(
    params: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("WANDB_API_KEY", "secret-key")  # in the shell, never forwarded
    monkeypatch.setenv("GIT_SHA", "c" * 40)
    data = repo_with_data(tmp_path, params)
    calls = dvc_reports(monkeypatch, {})
    assert main([*submit_argv(params, tmp_path), "--dry-run"]) == 0
    assert calls == [(tmp_path, "persona_clean")]
    captured = capsys.readouterr()
    assert "secret-key" not in captured.out
    spec = json.loads(captured.out)
    assert spec["display_name"] == "mirror-llm-finetune-adapter-v2"
    env = {e["name"]: e["value"] for e in spec["worker_pool_specs"][0]["container_spec"]["env"]}
    assert env == {  # GIT_SHA comes from the image
        "EXPECTED_DATA_SHA256": fingerprint(data),
        "WANDB_API_KEY_SECRET": "projects/mirror-ac215/secrets/wandb-api-key/versions/latest",
    }
    assert fingerprint(data) in captured.err


def test_submit_needs_the_local_dvc_data(params: dict, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="dvc pull"):
        main([*submit_argv(params, tmp_path), "--dry-run"])


def test_submit_refuses_stale_or_modified_data(
    params: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    repo_with_data(tmp_path, params)
    dvc_reports(
        monkeypatch,
        {"persona_clean": [{"changed outs": {"data/processed/persona/v1": "modified"}}]},
    )
    with pytest.raises(ValueError, match="not the current DVC version"):
        main([*submit_argv(params, tmp_path), "--dry-run"])
    assert capsys.readouterr().out == ""  # no spec printed, nothing submitted


def test_dvc_status_errors_are_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("dvc")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="dvc is not installed"):
        dvc_check.dvc_changes(tmp_path)

    def failing(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            ["dvc"], 255, "", "ERROR: you are not inside of a DVC repository"
        )

    monkeypatch.setattr(subprocess, "run", failing)
    with pytest.raises(RuntimeError, match="not inside of a DVC repository"):
        dvc_check.dvc_changes(tmp_path)


def test_job_spec_refuses_plain_secrets(params: dict) -> None:
    for name in ("WANDB_API_KEY", "HF_TOKEN"):
        with pytest.raises(ValueError, match="Secret Manager"):
            job_spec(params, "gs://b/d", {name: "value"})


def test_params_secrets_must_be_resource_names(params: dict) -> None:
    params["vertex"]["secrets"] = {"WANDB_API_KEY": "0123abcd-pasted-key"}
    with pytest.raises(ValueError, match="resource name"):
        secret_refs(params)


def test_job_reads_its_secrets_at_run_time() -> None:
    resource = "projects/p/secrets/wandb-api-key/versions/latest"
    env = {"WANDB_API_KEY_SECRET": resource}
    assert load_secrets(env, fetcher={resource: "the-key"}.__getitem__) == ["WANDB_API_KEY"]
    assert env["WANDB_API_KEY"] == "the-key"
    env = {"WANDB_API_KEY_SECRET": resource, "WANDB_API_KEY": "exported"}
    assert load_secrets(env, fetcher=lambda _: "unused") == []  # a local run keeps its own key
    assert env["WANDB_API_KEY"] == "exported"


def test_unreadable_secret_names_the_missing_role() -> None:
    def denied(_resource: str) -> str:
        raise PermissionError("403")

    with pytest.raises(RuntimeError, match="secretAccessor"):
        load_secrets({"WANDB_API_KEY_SECRET": "projects/p/secrets/s/versions/1"}, fetcher=denied)


@pytest.mark.parametrize("git_sha", [None, "", "unknown", "abc123"])
def test_training_refuses_without_the_image_git_sha(tmp_path: Path, git_sha: str | None) -> None:
    data = write_splits(tmp_path)
    env = {"EXPECTED_DATA_SHA256": fingerprint(data)}
    if git_sha is not None:
        env["GIT_SHA"] = git_sha
    with pytest.raises(ValueError, match="GIT_SHA"):
        preflight(data, env, upload=True)


def test_training_refuses_data_that_differs_from_dvc(tmp_path: Path) -> None:
    data = write_splits(tmp_path)
    env = {"GIT_SHA": "b" * 40, "EXPECTED_DATA_SHA256": "0" * 64}
    with pytest.raises(ValueError, match="does not match the DVC version"):
        preflight(data, env, upload=True)


def test_publishing_needs_the_expected_data_sha(tmp_path: Path) -> None:
    data = write_splits(tmp_path)
    with pytest.raises(ValueError, match="EXPECTED_DATA_SHA256"):
        preflight(data, {"GIT_SHA": "b" * 40}, upload=True)
    # A local run without --upload may skip it; the sha is still recorded.
    assert preflight(data, {"GIT_SHA": "b" * 40}, upload=False) == (
        "b" * 40,
        fingerprint(data),
    )


def test_preflight_passes_on_matching_data(tmp_path: Path) -> None:
    data = write_splits(tmp_path)
    env = {"GIT_SHA": "b" * 40, "EXPECTED_DATA_SHA256": fingerprint(data)}
    assert preflight(data, env, upload=True) == ("b" * 40, fingerprint(data))
