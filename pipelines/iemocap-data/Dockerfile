FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first so this layer is cached when only the code changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY params.yaml ./
RUN uv sync --frozen --no-dev

# Data is mounted at run time (e.g. -v "$PWD/data:/app/data"); it is never baked into the image.
ENTRYPOINT ["uv", "run", "mirror-iemocap-data", "--params", "params.yaml"]
