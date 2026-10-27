# GPU training image for Vertex AI. Build explicitly with: docker build --target train ...
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS train
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Dependencies first: this layer stays cached when only the code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra train
COPY src ./src
COPY params.yaml ./
RUN uv sync --frozen --no-dev --extra train
# Data and outputs come from GCS at run time (Cloud Storage FUSE); nothing is baked in.
ENTRYPOINT ["uv", "run", "--no-sync", "mirror-llm-finetune", "--params", "params.yaml"]

# Default target: the light image CI builds (no GPU stack); `submit --dry-run` works here.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS check
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY params.yaml ./
RUN uv sync --frozen --no-dev
ENTRYPOINT ["uv", "run", "--no-sync", "mirror-llm-finetune", "--params", "params.yaml"]
