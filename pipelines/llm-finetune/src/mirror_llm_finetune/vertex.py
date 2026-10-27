"""Submit the training container as a Vertex AI custom job (serverless training)."""

from __future__ import annotations

from typing import Any

from mirror_llm_finetune.config import gcs_to_fuse


def job_spec(params: dict[str, Any], data_uri: str, env: dict[str, str]) -> dict[str, Any]:
    """The worker pool for one GPU replica. Inside the job, gs:// paths are read and
    written through Cloud Storage FUSE (/gcs/<bucket>/...); the code only sees files."""
    vertex = params["vertex"]
    if not vertex.get("image_uri"):
        raise ValueError("vertex.image_uri is empty: build and push the train image first")
    if not data_uri.startswith("gs://"):
        raise ValueError("data_uri must be a gs:// path the job can read")
    return {
        "display_name": f"mirror-llm-finetune-{params['output']['adapter_name']}",
        "worker_pool_specs": [
            {
                "machine_spec": {
                    "machine_type": vertex["machine_type"],
                    "accelerator_type": vertex["accelerator_type"],
                    "accelerator_count": vertex["accelerator_count"],
                },
                "replica_count": 1,
                "container_spec": {
                    "image_uri": vertex["image_uri"],
                    "args": ["train", "--data-dir", gcs_to_fuse(data_uri), "--upload"],
                    "env": [{"name": k, "value": v} for k, v in sorted(env.items())],
                },
            }
        ],
    }


def submit(params: dict[str, Any], spec: dict[str, Any]) -> str:
    from google.cloud import aiplatform

    vertex = params["vertex"]
    aiplatform.init(
        project=vertex["project"],
        location=vertex["region"],
        staging_bucket=vertex["staging_bucket"],
    )
    job = aiplatform.CustomJob(
        display_name=spec["display_name"], worker_pool_specs=spec["worker_pool_specs"]
    )
    job.submit()
    return job.resource_name
