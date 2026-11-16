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
            "db.yaml",
            "api-gateway.yaml",
            "cv-service.yaml",
            "llm-service.yaml",
            "frontend.yaml",
            "ingress.yaml",
        ):
            self.assertIn(f"- {resource}", content)

    def test_gateway_is_single_replica_and_strips_api_prefix_before_upstream(self) -> None:
        gateway = (K8S / "api-gateway.yaml").read_text(encoding="utf-8")
        self.assertIn("replicas: 1", gateway)
        self.assertIn("handle_path /api/*", gateway)
        self.assertIn("reverse_proxy 127.0.0.1:8000", gateway)
        self.assertIn("route {", gateway)
        metrics = gateway.index("@metrics path /api/metrics*")
        proxy = gateway.index("handle_path /api/*")
        self.assertLess(metrics, proxy)
        self.assertIn("respond @metrics 404", gateway)
        self.assertIn("path: /api/health", gateway)
        self.assertIn("port: 8080", gateway)

    def test_database_is_stateful_and_persists_postgres_data(self) -> None:
        db = (K8S / "db.yaml").read_text(encoding="utf-8")
        self.assertIn("kind: StatefulSet", db)
        self.assertIn("volumeClaimTemplates:", db)
        self.assertIn("mountPath: /var/lib/postgresql/data", db)
        self.assertIn("- name: PGDATA", db)
        self.assertIn("value: /var/lib/postgresql/data/pgdata", db)

    def test_generated_operator_bundle_is_ignored_and_assets_are_ci_gated(self) -> None:
        ignored = (REPO / ".gitignore").read_text(encoding="utf-8")
        workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("infra/k8s/mirror-gke-rendered.yaml", ignored)
        self.assertIn("python3 infra/tests/test_m5_09_k8s_assets.py", workflow)

    def test_gke_managed_certificate_is_rendered_for_the_ingress(self) -> None:
        ingress = (K8S / "ingress.yaml").read_text(encoding="utf-8")
        certificate = (K8S / "managed-certificate.yaml").read_text(encoding="utf-8")
        kustomization = (K8S / "kustomization.yaml").read_text(encoding="utf-8")
        self.assertIn("networking.gke.io/managed-certificates: mirror-managed", ingress)
        self.assertNotIn("secretName: mirror-tls", ingress)
        self.assertIn("kind: ManagedCertificate", certificate)
        self.assertIn("${MIRROR_DOMAIN}", certificate)
        self.assertIn("- managed-certificate.yaml", kustomization)

    def test_operator_handoff_names_all_runtime_secrets_and_proxy_boundary(self) -> None:
        handoff = (K8S / "README.md").read_text(encoding="utf-8")
        for key in (
            "POSTGRES_PASSWORD",
            "MIRROR_DEMO_PASSWORD",
            "DATABASE_URL",
            "JWT_SIGNING_KEY",
            "TRUSTED_PROXY_IPS",
        ):
            self.assertIn(key, handoff)
        self.assertIn("127.0.0.1/32", handoff)
        self.assertIn("ManagedCertificate", handoff)

    def test_model_services_have_long_startup_probes_and_cv_identity_handoff(self) -> None:
        cv = (K8S / "cv-service.yaml").read_text(encoding="utf-8")
        llm = (K8S / "llm-service.yaml").read_text(encoding="utf-8")
        for content in (cv, llm):
            self.assertIn("startupProbe:", content)
            self.assertIn("failureThreshold: 120", content)
        self.assertIn("serviceAccountName: mirror-cv-service", cv)
        self.assertIn("MODEL_BUCKET", cv)
        self.assertIn("MODEL_OBJECT", cv)
        self.assertIn("MODEL_VERSION", cv)
        self.assertIn("iam.gke.io/gcp-service-account", cv)

    def test_render_script_supplies_image_and_nonsecret_runtime_coordinates(self) -> None:
        script = (K8S / "render.sh").read_text(encoding="utf-8")
        self.assertIn("MIRROR_IMAGE_REGISTRY", script)
        self.assertIn("MIRROR_IMAGE_REPOSITORY", script)
        self.assertIn("MIRROR_IMAGE_TAG", script)
        self.assertIn("MIRROR_DOMAIN", script)
        self.assertIn("MIRROR_CV_GSA", script)
        self.assertIn("kustomize build", script)

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
