"""mirror-persona-checks: ask the model (--llm-url) or re-check saved replies (--replies)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx
import yaml

from mirror_persona_checks.checks import ask, load_prompts, markdown, run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mirror-persona-checks")
    parser.add_argument("--params", type=Path, default=Path("params.yaml"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--llm-url", help="llm-service base URL, e.g. http://localhost:8002")
    source.add_argument("--replies", type=Path, help="replies.yaml from an earlier run")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args(argv)

    params = yaml.safe_load(args.params.read_text())
    if args.replies:
        replies = yaml.safe_load(args.replies.read_text())
    else:
        replies = []
        with httpx.Client(timeout=120) as client:
            for name, path in params["prompts"].items():
                for prompt in load_prompts(args.params.parent / path):
                    reply = ask(client, args.llm_url, params, prompt["message"])
                    replies.append({"set": name, **prompt, "reply": reply})

    report = run(replies, params)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "replies.yaml").write_text(
        yaml.safe_dump(replies, sort_keys=False, allow_unicode=True)
    )
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output_dir / "report.md").write_text(markdown(report))
    for name, counts in report["summary"].items():
        print(f"{name}: {counts['passed']} of {counts['total']} passed")
    return 0 if all(r["passed"] for r in report["results"]) else 1


if __name__ == "__main__":
    sys.exit(main())
