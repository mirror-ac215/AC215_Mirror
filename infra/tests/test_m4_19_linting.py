"""M4-19: repository-wide Ruff lint and formatting enforcement.

Run with:
    python3 infra/tests/test_m4_19_linting.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHON_SCOPE = ("services", "pipelines")


class M419LintingTests(unittest.TestCase):
    """Protect the shared Ruff policy and its fail-closed CI wiring."""

    def test_root_ruff_policy_covers_the_declared_python_scope(self) -> None:
        config = (REPO / "ruff.toml").read_text(encoding="utf-8")
        self.assertIn('"services/api-gateway",', config)
        self.assertIn('"pipelines/llm-eval/pairwise/src",', config)
        self.assertIn('"mirror_fairness_audit",', config)
        self.assertIn('target-version = "py311"', config)

    def test_ci_runs_lint_and_format_checks_for_all_python_components(self) -> None:
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = ci[ci.index("  python_lint:") : ci.index("  ci_summary:")]
        for command in (
            "ruff check --config ruff.toml services pipelines",
            "ruff format --config ruff.toml --check services pipelines",
        ):
            self.assertIn(command, job)

    def test_ci_summary_fails_closed_when_repository_linting_fails(self) -> None:
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        summary = ci[ci.index("  ci_summary:") :]
        self.assertIn("python_lint", summary)
        self.assertIn("PYTHON_LINT_RESULT", summary)
        self.assertIn('"$PYTHON_LINT_RESULT" != "success"', summary)


if __name__ == "__main__":
    unittest.main()
