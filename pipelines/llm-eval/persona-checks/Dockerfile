FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY params.yaml ./
COPY prompts ./prompts
RUN uv sync --frozen --no-dev

# Results are written to a mounted folder, e.g. -v "$PWD/outputs:/app/outputs".
ENTRYPOINT ["uv", "run", "--no-sync", "mirror-persona-checks", "--params", "params.yaml"]
