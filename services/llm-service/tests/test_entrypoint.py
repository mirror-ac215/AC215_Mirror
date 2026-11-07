import os
import subprocess
from pathlib import Path


def run_real_mode(tmp_path: Path, **settings: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    captured = tmp_path / "args.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_vllm = fake_bin / "vllm"
    fake_vllm.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURED_ARGS"\n')
    fake_vllm.chmod(0o755)

    environment = {k: v for k, v in os.environ.items() if k != "LORA_ADAPTER_PATH"} | {
        "CAPTURED_ARGS": str(captured),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        **settings,
    }
    entrypoint = Path(__file__).parents[1] / "docker-entrypoint.sh"
    result = subprocess.run(
        ["sh", str(entrypoint), "real"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, captured


def test_real_mode_passes_tunable_vllm_settings(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    result, captured = run_real_mode(
        tmp_path,
        LORA_ADAPTER_PATH=str(adapter),
        MAX_LORA_RANK="32",
        GPU_MEMORY_UTILIZATION="0.7",
        DTYPE="half",
    )

    assert result.returncode == 0, result.stderr
    arguments = captured.read_text().splitlines()
    assert "--enable-lora" in arguments
    assert ["--max-lora-rank", "32"] == arguments[arguments.index("--max-lora-rank") : arguments.index("--max-lora-rank") + 2]
    assert ["--gpu-memory-utilization", "0.7"] == arguments[arguments.index("--gpu-memory-utilization") : arguments.index("--gpu-memory-utilization") + 2]
    assert ["--dtype", "half"] == arguments[arguments.index("--dtype") : arguments.index("--dtype") + 2]


def test_real_mode_serves_the_plain_base_model_without_an_adapter(tmp_path: Path) -> None:
    result, captured = run_real_mode(tmp_path)

    assert result.returncode == 0, result.stderr
    arguments = captured.read_text().splitlines()
    assert arguments[:2] == ["serve", "Qwen/Qwen2.5-3B-Instruct"]
    assert not {"--enable-lora", "--lora-modules", "--max-lora-rank"} & set(arguments)
    assert ["--served-model-name", "mirror-persona-v1"] == arguments[arguments.index("--served-model-name") : arguments.index("--served-model-name") + 2]


def test_real_mode_refuses_a_missing_adapter_path(tmp_path: Path) -> None:
    result, captured = run_real_mode(tmp_path, LORA_ADAPTER_PATH=str(tmp_path / "missing"))

    assert result.returncode == 1
    assert "not found" in result.stderr
    assert not captured.exists()
