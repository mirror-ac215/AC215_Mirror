import json
import time
from collections.abc import Iterator
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.config import Settings
from app.logging_config import configure_logging, request_id_context

MOCK_REPLY = "That sounds like a lot to carry. What feels most pressing right now?"
MOCK_CHUNKS = (
    "That sounds like a lot to carry. ",
    "What feels most pressing right now?",
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=300, ge=1)
    temperature: float = Field(default=0.7, ge=0, le=2)
    stream: bool = False


def stream_completion(model: str, completion_id: str, created: int) -> Iterator[str]:
    chunks = (
        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
        *(
            {"index": 0, "delta": {"content": content}, "finish_reason": None}
            for content in MOCK_CHUNKS
        ),
        {"index": 0, "delta": {}, "finish_reason": "stop"},
    )
    for choice in chunks:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [choice],
        }
        yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
    yield "data: [DONE]\n\n"


def create_app() -> FastAPI:
    settings = Settings()
    logger = configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name)
    app.state.mock_request_count = 0

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={"path": request.url.path, "status_code": response.status_code},
            )
            return response
        finally:
            request_id_context.reset(token)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "mock"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            content=(
                "# TYPE mirror_llm_mock_requests_total counter\n"
                f"mirror_llm_mock_requests_total {app.state.mock_request_count}\n"
            ),
            media_type="text/plain; version=0.0.4",
        )

    @app.post("/v1/chat/completions", response_model=None)
    def create_completion(request: ChatRequest) -> object:
        app.state.mock_request_count += 1
        completion_id = f"chatcmpl-mock-{uuid4().hex}"
        created = int(time.time())
        if request.stream:
            return StreamingResponse(
                stream_completion(request.model, completion_id, created),
                media_type="text/event-stream",
            )
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": MOCK_REPLY},
                    "finish_reason": "stop",
                }
            ],
        }

    return app


app = create_app()
