FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install locked production dependencies before copying source for build caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# The gateway never downloads at runtime, so the pinned text emotion model ships in the image.
RUN uv run --no-sync python -c "from huggingface_hub import snapshot_download; from app.config import Settings as S; f = S.model_fields; snapshot_download(f['text_emotion_model'].default, revision=f['text_emotion_revision'].default, allow_patterns=['*.json', '*.txt', 'pytorch_model.bin'])"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
