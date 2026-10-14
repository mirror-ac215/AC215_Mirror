"""Executable contracts for M3-13 Stage A deployment assets.

These tests only validate committed assets with dummy values; they never call
cloud APIs that write resources.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


INFRA = Path(__file__).resolve().parents[1]
REPO = INFRA.parent
DUMMY_ENV = {
    **os.environ,
    "POSTGRES_PASSWORD": "dummy-postgres-password",
    "MIRROR_DEMO_PASSWORD": "dummy-demo-password",
    "CADDY_DOMAIN": "stage-a.example.test",
    "CADDY_EMAIL": "ops@example.test",
    "LLM_ADAPTER_HOST_PATH": "/tmp/stage-a-adapter",
}


def run(*command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO, env=env, text=True, capture_output=True, check=False)


class StageAAssetTests(unittest.TestCase):
    def test_provisioner_uses_a_dedicated_custom_vpc_and_validates_reused_resources(self) -> None:
        provisioner = (INFRA / "gcp" / "provision-t4-vm.sh").read_text()

        self.assertNotIn('M3_13_NETWORK="${M3_13_NETWORK:-default}"', provisioner)
        self.assertIn("Refusing to use GCP default VPC", provisioner)
        self.assertIn("--subnet-mode custom", provisioner)
        self.assertIn("gcloud compute networks describe", provisioner)
        self.assertIn("gcloud compute networks subnets describe", provisioner)
        self.assertIn("Firewall rule drift", provisioner)
        self.assertIn("VM drift", provisioner)
        self.assertIn('fail_drift "Address"', provisioner)
        self.assertIn("35.235.240.0/20", provisioner)

    def test_provisioner_rejects_active_non_managed_allow_ingress_that_can_target_the_vm(self) -> None:
        provisioner = (INFRA / "gcp" / "provision-t4-vm.sh").read_text()

        self.assertIn("validate_effective_ingress", provisioner)
        self.assertIn("gcloud compute firewall-rules list", provisioner)
        self.assertIn('--filter="network:$M3_13_NETWORK AND direction=INGRESS AND disabled=false"', provisioner)
        self.assertIn("M3_13_HTTP_FIREWALL_RULE", provisioner)
        self.assertIn("M3_13_HTTPS_FIREWALL_RULE", provisioner)
        self.assertIn("M3_13_IAP_SSH_FIREWALL_RULE", provisioner)
        self.assertIn('not target_tags or {"mirror-public", "mirror-iap-ssh"}.intersection(target_tags)', provisioner)
        self.assertIn("Non-managed ALLOW ingress", provisioner)

    def test_production_environment_file_is_ignored_but_example_is_trackable(self) -> None:
        ignored = run("git", "check-ignore", "-q", "infra/.env.prod")
        example = run("git", "check-ignore", "-q", "infra/.env.prod.example")

        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        self.assertEqual(example.returncode, 1, example.stderr)

    def test_bootstrapper_installs_nvidia_driver_and_requires_reboot_before_gpu_checks(self) -> None:
        bootstrapper = (INFRA / "gcp" / "bootstrap-vm.sh").read_text()

        self.assertIn("ubuntu-drivers", bootstrapper)
        self.assertIn("nvidia-driver-535", bootstrapper)
        self.assertIn("REBOOT_REQUIRED", bootstrapper)
        self.assertIn("reboot", bootstrapper)
        self.assertIn("docker run --rm --gpus all", bootstrapper)

    def test_bootstrapper_writes_one_complete_docker_apt_source_line(self) -> None:
        bootstrapper = (INFRA / "gcp" / "bootstrap-vm.sh").read_text()

        self.assertIn(
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable"',
            bootstrapper,
        )

    def test_provisioner_requires_approved_public_source_ranges(self) -> None:
        provisioner = (INFRA / "gcp" / "provision-t4-vm.sh").read_text()

        self.assertIn(
            "for variable in M3_13_PROJECT_ID M3_13_ZONE M3_13_SERVICE_ACCOUNT_EMAIL M3_13_PUBLIC_SOURCE_RANGES; do",
            provisioner,
        )
        self.assertIn(
            'ensure_firewall_rule "$M3_13_HTTP_FIREWALL_RULE" "$M3_13_PUBLIC_SOURCE_RANGES" "80" "mirror-public"',
            provisioner,
        )
        self.assertIn(
            'ensure_firewall_rule "$M3_13_HTTPS_FIREWALL_RULE" "$M3_13_PUBLIC_SOURCE_RANGES" "443" "mirror-public"',
            provisioner,
        )
        self.assertNotIn('"0.0.0.0/0" "80"', provisioner)
        self.assertNotIn('"0.0.0.0/0" "443"', provisioner)

    def test_stage_a_shell_scripts_parse(self) -> None:
        for script in (INFRA / "deploy-stage-a.sh", INFRA / "gcp" / "bootstrap-vm.sh", INFRA / "gcp" / "provision-t4-vm.sh"):
            result = run("bash", "-n", str(script))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_compose_resolves_to_only_caddy_public_ports_and_gpu_llm(self) -> None:
        result = run(
            "docker", "compose", "--env-file", "/dev/null", "--profile", "cv", "-f", "infra/compose.yml", "-f", "infra/compose.prod.yml", "config", "--format", "json", env=DUMMY_ENV
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        compose = json.loads(result.stdout)
        services = compose["services"]
        self.assertEqual(services["caddy"]["ports"], [{"mode": "ingress", "target": 80, "published": "80", "protocol": "tcp"}, {"mode": "ingress", "target": 443, "published": "443", "protocol": "tcp"}])
        for service in ("api-gateway", "frontend", "cv-service"):
            self.assertNotIn("ports", services[service])
        self.assertEqual(services["llm-service"]["gpus"], [{"count": -1}])

    def test_caddyfile_validates_with_dummy_runtime_values(self) -> None:
        result = run(
            "docker", "run", "--rm", "--network", "none", "-e", "CADDY_DOMAIN=stage-a.example.test", "-e", "CADDY_EMAIL=ops@example.test", "-v", f"{(INFRA / 'caddy' / 'Caddyfile').resolve()}:/etc/caddy/Caddyfile:ro", "caddy:2.10.2-alpine", "caddy", "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_frontend_build_accepts_public_relative_api_url(self) -> None:
        dockerfile = (REPO / "services" / "frontend" / "Dockerfile").read_text()
        self.assertIn("ARG VITE_API_BASE_URL", dockerfile)
        self.assertIn("ARG VITE_USE_MOCK_API", dockerfile)
        self.assertIn("ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}", dockerfile)
        self.assertIn("ENV VITE_USE_MOCK_API=${VITE_USE_MOCK_API}", dockerfile)

    def test_production_example_has_no_secret_values(self) -> None:
        example = (INFRA / ".env.prod.example").read_text()
        for variable in ("POSTGRES_PASSWORD=", "MIRROR_DEMO_PASSWORD=", "CADDY_DOMAIN=", "LLM_ADAPTER_HOST_PATH="):
            self.assertIn(variable, example)
        self.assertNotIn("replace-me", example.lower())
        self.assertNotIn("password123", example.lower())

    def test_ci_executes_stage_a_asset_tests(self) -> None:
        workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("python3 infra/tests/test_stage_a_assets.py", workflow)


if __name__ == "__main__":
    unittest.main()
