"""Render the 20 sample cases for team review (M3-08 definition of done).

Without --llm-url: shows each case's prompt (system prompt + patient message).
With --llm-url: also asks llm-service for Mirror's reply, giving one short
transcript per case.

    uv run python -m scripts.prompt_samples > prompt_samples.md
    uv run python -m scripts.prompt_samples --llm-url http://localhost:8002 > prompt_samples.md
"""

import argparse
import json
from pathlib import Path

import httpx

from app.prompt import PROMPT_VERSION, build_messages

CASES = Path(__file__).parent.parent / "tests" / "prompt_cases.json"


def ask_llm(llm_url: str, model: str, messages: list[dict[str, str]]) -> str:
    response = httpx.post(
        f"{llm_url}/v1/chat/completions",
        json={"model": model, "messages": messages, "max_tokens": 200},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm-url", help="llm-service base URL, e.g. http://localhost:8002"
    )
    parser.add_argument("--model", default="mirror-persona-v1")
    args = parser.parse_args()

    print(f"# Prompt samples ({PROMPT_VERSION})\n")
    print(
        "Review each reply: does it guess instead of state, ask when signals disagree,"
    )
    print("stay within 2-4 sentences, and never claim to be a person or a clinician?\n")
    for number, case in enumerate(json.loads(CASES.read_text()), start=1):
        messages = build_messages(case["context"], case["message"], case.get("history"))
        print(f"## {number}. {case['situation']} (`{case['id']}`)\n")
        print("```text")
        print(messages[0]["content"].split("Signals for this turn:\n")[1])
        print("```\n")
        for item in messages[1:]:
            speaker = "Patient" if item["role"] == "user" else "Mirror"
            print(f"**{speaker}:** {item['content']}\n")
        if args.llm_url:
            print(f"**Mirror:** {ask_llm(args.llm_url, args.model, messages)}\n")
        print("Reviewer notes:\n")


if __name__ == "__main__":
    main()
