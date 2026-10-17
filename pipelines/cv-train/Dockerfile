FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Dependencies first so this layer is cached when only the code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY params.yaml ./
RUN uv sync --frozen --no-dev
# Data and outputs are mounted at run time (see README); nothing is baked into the image.
ENTRYPOINT ["uv", "run", "--no-sync", "mirror-cv-train", "--params", "params.yaml"]
