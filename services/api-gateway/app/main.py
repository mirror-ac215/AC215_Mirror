from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.chat import router as chat_router
from app.config import Settings
from app.health import check_dependencies
from app.logging_config import configure_logging, request_id_context

settings = Settings()
logger = configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(chat_router)

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
async def health() -> dict[str, object]:
    """Gateway is alive; each dependency is reported separately (contract:/health)."""
    dependencies = await check_dependencies(settings)
    status = "ok" if all(state == "ok" for state in dependencies.values()) else "degraded"
    return {"status": status, "dependencies": dependencies}



@app.get("/metrics")
def metrics() -> Response:
    """Placeholder for service-specific metrics added by each component owner."""

    return Response(
        content="# Service-specific metrics are added by each component owner.\n",
        media_type="text/plain; version=0.0.4",
    )
