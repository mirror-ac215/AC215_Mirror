"""Ask the model every prompt, then check each reply against fixed rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import yaml

SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")
CLAUSE_END = re.compile(r"[.,;:!?]")
NEGATION_WINDOW = 6  # words before a match, within the same clause


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


def is_negated(reply: str, start: int, negation: re.Pattern[str]) -> bool:
    """True if a negation word sits in the few words before `start`, in the same clause.

    "Please don't double your pills" is negated; "Don't worry, just double your pills"
    is not, because the comma ends the clause that holds "Don't".
    """
    clause = CLAUSE_END.split(reply[:start])[-1]
    return bool(negation.search(" ".join(clause.split()[-NEGATION_WINDOW:])))


def rule_hits(
    reply: str,
    rules: dict[str, re.Pattern[str]],
    negation: re.Pattern[str] | None = None,
    negatable: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
    """(rules broken, rules to review by hand).

    A rule in `negatable` whose every match follows a negation ("don't double your pills")
    goes to review instead of failing: it is usually a correct refusal.
    """
    reply = reply.replace("\u2019", "'")  # curly apostrophes, as models often write them
    broken, review = [], []
    for name, pattern in rules.items():
        starts = [m.start() for m in pattern.finditer(reply)]
        if not starts:
            continue
        if negation and name in negatable and all(is_negated(reply, s, negation) for s in starts):
            review.append(name)
        else:
            broken.append(name)
    return broken, review


def check_reply(
    reply: str,
    rules: dict[str, re.Pattern[str]],
    max_sentences: int,
    negation: re.Pattern[str] | None = None,
    negatable: frozenset[str] = frozenset(),
) -> list[str]:
    """Names of the rules the reply breaks; an empty list means it passes."""
    broken, _ = rule_hits(reply, rules, negation, negatable)
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
    negation = re.compile(params["negation"], re.IGNORECASE)
    negatable = frozenset(params["distress_rules"])  # identity rules match training: unchanged
    results = []
    for item in replies:
        rules = identity if item["set"] == "identity" else distress
        broken = check_reply(item["reply"], rules, params["max_sentences"], negation, negatable)
        _, review = rule_hits(item["reply"], rules, negation, negatable)
        results.append({**item, "broken": broken, "review": review, "passed": not broken})
    summary = {}
    for name in ("identity", "distress"):
        subset = [r for r in results if r["set"] == name]
        summary[name] = {
            "total": len(subset),
            "passed": sum(r["passed"] for r in subset),
            "to_review": sum(bool(r["review"]) for r in subset),
        }
    return {"model": params["model"], "summary": summary, "results": results}


def markdown(report: dict[str, Any]) -> str:
    lines = [f"# Persona checks: {report['model']}", ""]
    for name, counts in report["summary"].items():
        lines.append(
            f"- {name}: {counts['passed']} of {counts['total']} passed, "
            f"{counts['to_review']} to review by hand"
        )
    failed = [r for r in report["results"] if not r["passed"]]
    lines += ["", "## Failed" if failed else "No reply broke a rule.", ""]
    for r in failed:
        lines += [
            f"**{r['id']}** ({', '.join(r['broken'])}): {r['message']}",
            "",
            f"> {r['reply']}",
            "",
        ]
    review = [r for r in report["results"] if r["passed"] and r["review"]]
    if review:
        lines += ["## To review by hand (rule matched after a negation)", ""]
        for r in review:
            lines += [
                f"**{r['id']}** ({', '.join(r['review'])}): {r['message']}",
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
