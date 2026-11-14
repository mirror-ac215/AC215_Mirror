"""M5-09 repository assets for a Mostafa-operated GKE deployment.

Run with:
    python3 infra/tests/test_m5_09_k8s_assets.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
K8S = REPO / "infra" / "k8s"


class M509KubernetesAssetTests(unittest.TestCase):
    """Protect the local repository handoff, without contacting GKE."""

    def test_kustomization_declares_the_namespace_and_all_runtime_services(self) -> None:
        content = (K8S / "kustomization.yaml").read_text(encoding="utf-8")
        self.assertIn("namespace: mirror", content)
        for resource in (
            "namespace.yaml",
            "api-gateway.yaml",
            "cv-service.yaml",
            "llm-service.yaml",
            "frontend.yaml",
            "ingress.yaml",
        ):
            self.assertIn(f"- {resource}", content)

    def test_llm_deployment_is_the_only_gpu_scheduled_workload(self) -> None:
        llm = (K8S / "llm-service.yaml").read_text(encoding="utf-8")
        self.assertIn("nvidia.com/gpu", llm)
        self.assertIn("cloud.google.com/gke-accelerator", llm)
        for name in ("api-gateway.yaml", "cv-service.yaml", "frontend.yaml"):
            self.assertNotIn("nvidia.com/gpu", (K8S / name).read_text(encoding="utf-8"))

    def test_images_are_immutable_and_never_embed_registry_credentials(self) -> None:
        for name in ("api-gateway.yaml", "cv-service.yaml", "llm-service.yaml", "frontend.yaml"):
            content = (K8S / name).read_text(encoding="utf-8")
            self.assertIn("${MIRROR_IMAGE_TAG}", content)
            self.assertNotIn("password:", content.lower())
            self.assertNotIn("service-account.json", content.lower())

    def test_operator_handoff_forbids_paid_cloud_execution_by_owen(self) -> None:
        handoff = (K8S / "README.md").read_text(encoding="utf-8")
        self.assertIn("Mostafa", handoff)
        self.assertIn("must not", handoff.lower())
        self.assertIn("stopped-state confirmation", handoff)


if __name__ == "__main__":
    unittest.main()
