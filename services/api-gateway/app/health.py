""" Checks whether the services the gateway depends on are reachable."""

import asyncio

import httpx

from app.config import Settings


async def check_http(base_url: str, timeout_s: float) -> str:
    """'ok' if GET <base_url>/health answers 200, otherwise 'down'."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(f"{base_url}/health")
        return "ok" if response.status_code == 200 else "down"
    except httpx.HTTPError:
        return "down"

async def check_tcp(host: str, port: int, timeout_s: float) -> str:
    """'ok' if sometghing accepts a connection on host:port (used for Postgres)."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_s)
        writer.close()
        await writer.wait_closed()
        return "ok"
    except (OSError, TimeoutError):
        return "down"

async def check_dependencies(settings: Settings) -> dict[str, str]:
    """Check all dependencies at the same time and report each one."""
    cv, llm, db = await asyncio.gather(
        check_http(settings.cv_service_url, settings.dependency_timeout_s),
        check_http(settings.llm_service_url, settings.dependency_timeout_s),
        check_tcp(settings.db_host, settings.db_port, settings.dependency_timeout_s),
    )
    return {"cv-service": cv, "llm-service": llm, "db": db}