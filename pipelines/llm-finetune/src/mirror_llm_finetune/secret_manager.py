"""Secrets for the training job, read from Secret Manager at run time.

The Vertex job spec carries only each secret's resource name, e.g.
WANDB_API_KEY_SECRET=projects/mirror-ac215/secrets/wandb-api-key/versions/latest,
never the value: anyone who can view the job in the console sees no key. The job
reads the value with its own service account just before training starts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

SUFFIX = "_SECRET"
# Never passed to the job as plain environment variables.
SECRET_NAMES = frozenset({"WANDB_API_KEY", "HF_TOKEN"})


def secret_refs(params: Mapping[str, Any]) -> dict[str, str]:
    """vertex.secrets in params.yaml -> job env entries holding resource names only."""
    refs = params["vertex"].get("secrets") or {}
    for name, resource in refs.items():
        if not str(resource).startswith("projects/"):
            raise ValueError(
                f"vertex.secrets.{name} must be a Secret Manager resource name "
                "(projects/<project>/secrets/<name>/versions/<version>), never the secret itself"
            )
    return {f"{name}{SUFFIX}": str(resource) for name, resource in sorted(refs.items())}


def fetch(resource: str) -> str:
    """Read one secret version with the caller's credentials (the job's service account)."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    return client.access_secret_version(name=resource).payload.data.decode("utf-8").strip()


def load_secrets(
    env: MutableMapping[str, str],
    fetcher: Callable[[str], str] = fetch,
) -> list[str]:
    """For every NAME_SECRET in env, set NAME from Secret Manager. Returns the names set.

    A NAME already in env is kept: a local run can still use an exported key.
    """
    loaded = []
    for key in sorted(k for k in env if k.endswith(SUFFIX)):
        name = key.removesuffix(SUFFIX)
        if env.get(name):
            continue
        try:
            env[name] = fetcher(env[key])
        except Exception as err:
            raise RuntimeError(
                f"cannot read {env[key]} for {name}: the job's service account needs "
                "roles/secretmanager.secretAccessor on that secret (see README)"
            ) from err
        loaded.append(name)
    return loaded
