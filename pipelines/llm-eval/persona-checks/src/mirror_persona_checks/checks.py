"""Ask the model every prompt, then check each reply against fixed rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import yaml

SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")


def load_prompts(path: Path) -> list[dict[str, str]]:
    prompts = yaml.safe_load(path.read_text())
    ids = [p["id"] for p in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate prompt ids")
    return prompts


def compile_rules(rules: dict[str, str]) -> dict[str, re.Pattern[str]]:
    return {name: re.compile(pattern, re.IGNORECASE) for name, pattern in rules.items()}


def count_sentences(text: str) -> int:
    return len(SENTENCE_END.findall(text.strip() + " "))


def check_reply(reply: str, rules: dict[str, re.Pattern[str]], max_sentences: int) -> list[str]:
    """Names of the rules the reply breaks; an empty list means it passes."""
    broken = [name for name, pattern in rules.items() if pattern.search(reply)]
    if not reply.strip():
        broken.append("empty")
    elif count_sentences(reply) > max_sentences:
        broken.append("too_long")
    return broken


def ask(client: httpx.Client, llm_url: str, params: dict[str, Any], message: str) -> str:
    response = client.post(
        f"{llm_url}/v1/chat/completions",
        json={
            "model": params["model"],
            "messages": [
                {"role": "system", "content": params["system_prompt"]},
                {"role": "user", "content": message},
            ],
            "max_tokens": params["max_tokens"],
            "temperature": params["temperature"],
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def run(replies: list[dict[str, str]], params: dict[str, Any]) -> dict[str, Any]:
    """Check saved replies. Each item has set, id, message and reply."""
    identity = compile_rules(params["identity_rules"])
    distress = {**identity, **compile_rules(params["distress_rules"])}
    results = []
    for item in replies:
        rules = identity if item["set"] == "identity" else distress
        broken = check_reply(item["reply"], rules, params["max_sentences"])
        results.append({**item, "broken": broken, "passed": not broken})
    summary = {}
    for name in ("identity", "distress"):
        subset = [r for r in results if r["set"] == name]
        summary[name] = {"total": len(subset), "passed": sum(r["passed"] for r in subset)}
    return {"model": params["model"], "summary": summary, "results": results}


def markdown(report: dict[str, Any]) -> str:
    lines = [f"# Persona checks: {report['model']}", ""]
    for name, counts in report["summary"].items():
        lines.append(f"- {name}: {counts['passed']} of {counts['total']} passed")
    failed = [r for r in report["results"] if not r["passed"]]
    lines += ["", "## Failed" if failed else "No reply broke a rule.", ""]
    for r in failed:
        lines += [
            f"**{r['id']}** ({', '.join(r['broken'])}): {r['message']}",
            "",
            f"> {r['reply']}",
            "",
        ]
    lines += [
        "Rules can miss a bad reply. Read every reply in replies.yaml once and note anything",
        "the rules did not catch in the PR.",
        "",
    ]
    return "\n".join(lines)
