"""M4-21: one command starts the local stack, and production never uses the local defaults.

Runs `docker compose config` only: nothing is built or started.
    python3 infra/tests/test_m4_21_one_command.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
REPO = INFRA.parent
CONFIG_VARS = ("DB_NAME", "DB_USER", "DB_PASSWORD", "MIRROR_DEMO_PASSWORD", "JWT_SIGNING_KEY")
PROD_VALUES = {
    "DB_NAME": "prod_db",
    "DB_USER": "prod_user",
    "DB_PASSWORD": "prod-only-db-password",
    "MIRROR_DEMO_PASSWORD": "prod-only-demo-password",
    "JWT_SIGNING_KEY": "prod-only-jwt-signing-key-with-adequate-length",
    "CADDY_DOMAIN": "mirror.example.test",
}


def clean_env() -> dict[str, str]:
    """The caller's environment without any Mirror configuration variable."""
    return {k: v for k, v in os.environ.items() if k not in CONFIG_VARS and k != "CADDY_DOMAIN"}


def compose_config(
    *files: str, extra: dict[str, str] | None = None, profiles: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    # An empty --env-file stops Compose from reading a developer's own infra/.env.
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "empty.env"
        empty.write_text("")
        command = ["docker", "compose", "--env-file", str(empty)]
        for profile in profiles:
            command += ["--profile", profile]
        for f in files:
            command += ["-f", f]
        command += ["config", "--format", "json"]
        return subprocess.run(
            command, cwd=REPO, env=clean_env() | (extra or {}),
            text=True, capture_output=True, check=False,
        )


class OneCommandStartTests(unittest.TestCase):
    def test_local_stack_resolves_with_no_configuration(self) -> None:
        result = compose_config("infra/compose.yml")
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        db = services["db"]["environment"]
        gateway = services["api-gateway"]["environment"]
        # Gateway and database must agree on one identity, or login fails at runtime.
        self.assertEqual(
            gateway["DATABASE_URL"],
            f"postgresql://{db['POSTGRES_USER']}:{db['POSTGRES_PASSWORD']}@db:5432/{db['POSTGRES_DB']}",
        )
        self.assertTrue(db["MIRROR_DEMO_PASSWORD"])
        # The gateway rejects a signing key shorter than 32 characters (app/config.py).
        self.assertGreaterEqual(len(gateway["JWT_SIGNING_KEY"]), 32)

    def test_every_local_profile_publishes_only_loopback_ports(self) -> None:
        for profiles in ((), ("cv",)):
            with self.subTest(profiles=profiles):
                result = compose_config("infra/compose.yml", profiles=profiles)
                self.assertEqual(result.returncode, 0, result.stderr)
                services = json.loads(result.stdout)["services"]
                for name, service in services.items():
                    for port in service.get("ports", []):
                        self.assertEqual(
                            port.get("host_ip"),
                            "127.0.0.1",
                            f"{name} publishes {port['published']} outside loopback",
                        )

    def test_evidence_reproduction_uses_the_current_no_setup_quick_start(self) -> None:
        evidence = (REPO / "docs" / "evidence" / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("`.env` with two values", evidence)
        self.assertIn("no setup", evidence.lower())

    def test_production_refuses_to_start_when_any_value_is_missing(self) -> None:
        for missing in CONFIG_VARS:
            with self.subTest(missing=missing):
                values = {k: v for k, v in PROD_VALUES.items() if k != missing}
                result = compose_config("infra/compose.yml", "infra/compose.prod.yml", extra=values)
                self.assertNotEqual(result.returncode, 0, f"production started without {missing}")
                self.assertIn(missing, result.stderr)

    def test_production_uses_its_own_values_never_the_local_defaults(self) -> None:
        local = json.loads(compose_config("infra/compose.yml").stdout)["services"]
        result = compose_config("infra/compose.yml", "infra/compose.prod.yml", extra=PROD_VALUES)
        self.assertEqual(result.returncode, 0, result.stderr)
        prod = json.loads(result.stdout)["services"]
        self.assertEqual(prod["db"]["environment"]["POSTGRES_PASSWORD"], PROD_VALUES["DB_PASSWORD"])
        self.assertEqual(prod["api-gateway"]["environment"]["JWT_SIGNING_KEY"], PROD_VALUES["JWT_SIGNING_KEY"])
        for service in ("db", "api-gateway"):
            local_values = set(local[service]["environment"].values())
            prod_values = set(prod[service]["environment"].values())
            for secret in ("POSTGRES_PASSWORD", "MIRROR_DEMO_PASSWORD", "JWT_SIGNING_KEY"):
                value = local[service]["environment"].get(secret)
                if value:
                    self.assertNotIn(value, prod_values, f"{service} kept the local {secret}")
            self.assertTrue(local_values)

    def test_ci_smoke_test_starts_the_stack_without_configuration(self) -> None:
        # The CI compose job proves the M4 "no manual configuration" rule, so it must not
        # set the values a fresh clone would lack.
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = ci[ci.index("  compose:"):ci.index("  ci_summary:")]
        for name in CONFIG_VARS:
            self.assertNotIn(f"{name}:", job, f"the compose CI job sets {name}")
        self.assertIn("python3 infra/tests/test_m4_21_one_command.py", job)


if __name__ == "__main__":
    unittest.main()
