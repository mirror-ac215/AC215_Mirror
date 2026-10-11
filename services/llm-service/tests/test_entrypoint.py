import os
import subprocess
from pathlib import Path


def test_real_mode_passes_tunable_vllm_settings(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    captured = tmp_path / "args.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_vllm = fake_bin / "vllm"
    fake_vllm.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURED_ARGS"\n')
    fake_vllm.chmod(0o755)

    environment = os.environ | {
        "LORA_ADAPTER_PATH": str(adapter),
        "MAX_LORA_RANK": "32",
        "GPU_MEMORY_UTILIZATION": "0.7",
        "DTYPE": "half",
        "CAPTURED_ARGS": str(captured),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    entrypoint = Path(__file__).parents[1] / "docker-entrypoint.sh"
    result = subprocess.run(
        ["sh", str(entrypoint), "real"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    arguments = captured.read_text().splitlines()
    assert ["--max-lora-rank", "32"] == arguments[arguments.index("--max-lora-rank") : arguments.index("--max-lora-rank") + 2]
    assert ["--gpu-memory-utilization", "0.7"] == arguments[arguments.index("--gpu-memory-utilization") : arguments.index("--gpu-memory-utilization") + 2]
    assert ["--dtype", "half"] == arguments[arguments.index("--dtype") : arguments.index("--dtype") + 2]
