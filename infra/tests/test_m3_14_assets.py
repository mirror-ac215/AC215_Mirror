#!/usr/bin/env python3
"""Regression checks for the M3-14 immutable Artifact Registry delivery assets."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-artifact-registry-images.yml"
REGISTRY_OVERRIDE = ROOT / "infra" / "compose.registry.yml"
DEPLOY_SCRIPT = ROOT / "infra" / "deploy-stage-b.sh"
PROD_EXAMPLE = ROOT / "infra" / ".env.prod.example"
INFRA_README = ROOT / "infra" / "README.md"
CLEANUP_POLICY = ROOT / "infra" / "artifact-registry-cleanup-policy.json"


def require_text(path: Path, *snippets: str) -> str:
    """Return a text asset after asserting every required safety marker."""
    assert path.is_file(), f"missing required M3-14 asset: {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8")
    for snippet in snippets:
        assert snippet in text, f"{path.relative_to(ROOT)} is missing: {snippet!r}"
    return text


def test_publish_workflow_uses_main_sha_tags_and_oidc() -> None:
    """Publishing must be main-only, immutable, and free of static cloud keys."""
    text = require_text(
        WORKFLOW,
        "push:",
        "branches: [main]",
        "workflow_dispatch:",
        "id-token: write",
        "contents: read",
        "google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093",
        "docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9",
        "docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8",
        "github.sha",
        "platforms: linux/amd64",
        "GAR_LOCATION",
        "GAR_REPOSITORY",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "GCP_SERVICE_ACCOUNT",
    )
    assert "GOOGLE_CREDENTIALS" not in text
    assert "service_account_key" not in text
    assert "push: ${{ github.event_name != 'pull_request' }}" in text


def test_publish_workflow_executes_tests_and_skips_unconfigured_publishing() -> None:
    """CI must execute M3-14 tests and leave main green before cloud setup exists."""
    ci = require_text(
        ROOT / ".github" / "workflows" / "ci.yml",
        "python3 infra/tests/test_m3_14_assets.py",
    )
    workflow = require_text(
        WORKFLOW,
        "ready: ${{ steps.configuration.outputs.ready }}",
        "Repository configuration is incomplete; skipping image publication.",
        "if: needs.validate_configuration.outputs.ready == 'true'",
        "project_id: ${{ vars.GCP_PROJECT_ID }}",
        "Reclaim runner disk space for CUDA image build",
        "Remove local CUDA BuildKit cache after publication",
        "minimum_free_kb=25000000",
    )
    assert 'if __name__ == "__main__":' in Path(__file__).read_text(encoding="utf-8")
    assert workflow.count("if: needs.validate_configuration.outputs.ready == 'true'") == 2


def test_registry_override_requires_sha_tagged_images() -> None:
    """Production registry delivery must never silently fall back to local builds."""
    text = require_text(
        REGISTRY_OVERRIDE,
        "MIRROR_IMAGE_REGISTRY:?set MIRROR_IMAGE_REGISTRY",
        "MIRROR_IMAGE_REPOSITORY:?set MIRROR_IMAGE_REPOSITORY",
        "MIRROR_IMAGE_TAG:?set MIRROR_IMAGE_TAG",
        "api-gateway:",
        "cv-service:",
        "db:",
        "frontend:",
        "llm-service:",
        "build: !reset null",
    )
    assert "latest" not in text


def test_stage_b_deployer_pulls_without_building() -> None:
    """The VM helper must pull an immutable tag and reject source/tag mismatch."""
    text = require_text(
        DEPLOY_SCRIPT,
        "docker compose",
        "compose.registry.yml",
        "pull",
        "up -d --no-build --wait",
        "MIRROR_IMAGE_TAG",
        "git rev-parse HEAD",
        'cd "$(dirname "$0")/.."',
    )
    assert "--build" not in text


def test_cleanup_policy_keeps_recent_images_and_expires_old_versions() -> None:
    """Registry retention must cap immutable-image storage without CI admin access."""
    policies = json.loads(CLEANUP_POLICY.read_text(encoding="utf-8"))
    assert {
        "name": "keep-most-recent-mirror-images",
        "action": {"type": "Keep"},
        "mostRecentVersions": {
            "packageNamePrefixes": ["mirror-"],
            "keepCount": 10,
        },
    } in policies
    assert {
        "name": "delete-old-mirror-images",
        "action": {"type": "Delete"},
        "condition": {
            "packageNamePrefixes": ["mirror-"],
            "tagState": "any",
            "olderThan": "30d",
        },
    } in policies


def test_registry_override_resolves_with_nonsecret_values() -> None:
    """Compose must resolve a registry deployment using placeholders only."""
    env = os.environ | {
        "POSTGRES_PASSWORD": "ci-only-password",
        "MIRROR_DEMO_PASSWORD": "ci-only-demo-password",
        "CADDY_DOMAIN": "mirror.example.test",
        "LLM_ADAPTER_HOST_PATH": "/tmp/mirror-adapter",
        "MIRROR_IMAGE_REGISTRY": "us-central1-docker.pkg.dev",
        "MIRROR_IMAGE_REPOSITORY": "mirror-project/mirror-images",
        "MIRROR_IMAGE_TAG": "a" * 40,
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "cv",
            "-f",
            "infra/compose.yml",
            "-f",
            "infra/compose.prod.yml",
            "-f",
            "infra/compose.registry.yml",
            "config",
            "--quiet",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_documentation_names_required_configuration_and_vm_evidence() -> None:
    """Operators need the exact non-secret configuration and verification path."""
    require_text(
        PROD_EXAMPLE,
        "MIRROR_IMAGE_REGISTRY=",
        "MIRROR_IMAGE_REPOSITORY=",
        "MIRROR_IMAGE_TAG=",
    )
    require_text(
        INFRA_README,
        "M3-14",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "MIRROR_IMAGE_TAG",
        "Artifact Registry",
        "artifact-registry-cleanup-policy.json",
        "set-cleanup-policies",
        "--dry-run",
        "--no-dry-run",
        "Data Access `DATA_WRITE` audit logging",
    )


if __name__ == "__main__":
    """Run the dependency-free M3-14 regression checks in GitHub Actions."""
    tests = [
        test_publish_workflow_uses_main_sha_tags_and_oidc,
        test_publish_workflow_executes_tests_and_skips_unconfigured_publishing,
        test_registry_override_requires_sha_tagged_images,
        test_stage_b_deployer_pulls_without_building,
        test_cleanup_policy_keeps_recent_images_and_expires_old_versions,
        test_registry_override_resolves_with_nonsecret_values,
        test_documentation_names_required_configuration_and_vm_evidence,
    ]
    for test in tests:
        test()
    print(f"M3-14 asset checks passed: {len(tests)}")
