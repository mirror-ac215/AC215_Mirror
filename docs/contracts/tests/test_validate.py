"""Acceptance tests for the contract-validation command."""

from __future__ import annotations

import subprocess
import sys
import importlib.util
import os
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).parents[1]


def test_validation_command_checks_schema_examples_and_all_openapi_specs() -> None:
    result = subprocess.run(
        [sys.executable, "validate.py"],
        cwd=CONTRACTS_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS context_object.valid.json" in result.stdout
    assert "PASS context_object.invalid.json" in result.stdout
    assert "PASS api-gateway.openapi.yaml" in result.stdout
    assert "PASS cv-service.openapi.yaml" in result.stdout
    assert "PASS llm-service.openapi.yaml" in result.stdout


def test_ci_runs_contract_validation_and_fails_closed_when_contracts_change() -> None:
    import yaml

    workflow_path = CONTRACTS_DIR.parents[1] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert "docs_contracts" in jobs["changes"]["outputs"]
    assert "contract_validation" in jobs
    assert "docs_contracts" in jobs["contract_validation"]["if"]
    assert "contract_validation" in jobs["ci_summary"]["needs"]
    summary_environment = jobs["ci_summary"]["steps"][0]["env"]
    assert "CONTRACT_VALIDATION_RESULT" in summary_environment
    summary_script = jobs["ci_summary"]["steps"][0]["run"]
    assert '[ "$DOCS_CONTRACTS_CHANGED" = "true" ] && [ "$CONTRACT_VALIDATION_RESULT" != "success" ]' in summary_script
    assert 'echo "Contract validation did not pass: $CONTRACT_VALIDATION_RESULT"' in summary_script
    assert 'exit 1' in summary_script


def test_contract_documentation_has_one_canonical_workflow() -> None:
    repository_root = CONTRACTS_DIR.parents[1]
    architecture = (repository_root / "docs" / "architecture.md").read_text(encoding="utf-8")
    project_context = (repository_root / "docs" / "PROJECT_CONTEXT.md").read_text(
        encoding="utf-8"
    )
    contract_readme = (CONTRACTS_DIR / "README.md").read_text(encoding="utf-8")

    assert "contracts/README.md" in architecture
    assert "uv run docs/contracts/validate.py" not in architecture
    assert "uvx --from openapi-spec-validator" not in architecture
    assert "cd docs/contracts\nuv run python validate.py" in contract_readme
    assert "uvx --from openapi-spec-validator" not in contract_readme
    assert "Run `uv` commands from that component's folder" in project_context


def test_openapi_discovery_includes_a_future_contract_file(tmp_path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("contract_validate", CONTRACTS_DIR / "validate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    future_contract = tmp_path / "future-service.openapi.yaml"
    future_contract.write_text(
        'openapi: 3.0.3\ninfo: {title: Future service, version: "1"}\npaths: {}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "HERE", tmp_path)

    assert module.openapi_contract_paths() == [future_contract]


def test_openapi_validation_rejects_an_invalid_future_contract(tmp_path, monkeypatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location("contract_validate", CONTRACTS_DIR / "validate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    invalid_contract = tmp_path / "future-service.openapi.yaml"
    invalid_contract.write_text(
        'openapi: 3.0.3\ninfo: {title: Future service}\npaths: []\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "HERE", tmp_path)

    assert not module.validate_openapi_contracts()
    assert "FAIL future-service.openapi.yaml" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("changes_result", "contract_result", "expected_exit"),
    [
        ("success", "success", 0),
        ("success", "failure", 1),
        ("success", "cancelled", 1),
        ("success", "skipped", 1),
        ("failure", "success", 1),
    ],
)
def test_ci_summary_script_rejects_unsuccessful_required_results(
    changes_result: str, contract_result: str, expected_exit: int
) -> None:
    import yaml

    workflow_path = CONTRACTS_DIR.parents[1] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    summary_script = workflow["jobs"]["ci_summary"]["steps"][0]["run"]
    environment = {
        **os.environ,
        "CHANGES_RESULT": changes_result,
        "SERVICE_TEMPLATE_CHANGED": "false",
        "SERVICE_TEMPLATE_RESULT": "skipped",
        "DB_CHANGED": "false",
        "DB_RESULT": "skipped",
        "DOCS_CONTRACTS_CHANGED": "true",
        "CONTRACT_VALIDATION_RESULT": contract_result,
        "PYTHON_LINT_RESULT": "success",
    }

    result = subprocess.run(
        ["sh", "-c", summary_script],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert result.returncode == expected_exit, result.stdout + result.stderr
