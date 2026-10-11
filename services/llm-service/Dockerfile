# GPU real-mode image. Build explicitly with: docker build --target real ...
FROM vllm/vllm-openai:v0.11.0 AS real

WORKDIR /app
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV MOCK_MODE=0 \
    MODEL_NAME=Qwen/Qwen2.5-3B-Instruct \
    SERVED_MODEL_NAME=mirror-persona-v1 \
    LORA_ADAPTER_PATH=/models/adapter-v1 \
    MAX_MODEL_LEN=2048 \
    MAX_NUM_SEQS=1 \
    PORT=8002

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# The default target is the portable deterministic mock server for laptops and CI.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS mock

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    MOCK_MODE=1 \
    PORT=8002

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh && uv sync --frozen --no-dev

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
