import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_mock_mode_health_reports_ready_without_model_loading(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock"}


@pytest.mark.anyio
async def test_mock_mode_returns_a_deterministic_openai_completion(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    request = {
        "model": "mirror-persona-v1",
        "messages": [{"role": "user", "content": "I am overwhelmed today."}],
        "max_tokens": 30,
        "temperature": 0.7,
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/chat/completions", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"].startswith("chatcmpl-mock-")
    assert payload["object"] == "chat.completion"
    assert isinstance(payload["created"], int)
    assert payload["model"] == "mirror-persona-v1"
    assert payload["choices"] == [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "That sounds like a lot to carry. What feels most pressing right now?",
            },
            "finish_reason": "stop",
        }
    ]


@pytest.mark.anyio
async def test_mock_mode_streams_openai_chunks_and_done_sentinel(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    request = {
        "model": "mirror-persona-v1",
        "messages": [{"role": "user", "content": "I am overwhelmed today."}],
        "stream": True,
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/chat/completions", json=request)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1] == "[DONE]"

    chunks = [json.loads(event) for event in events[:-1]]
    completion_ids = {chunk["id"] for chunk in chunks}
    assert len(completion_ids) == 1
    assert next(iter(completion_ids)).startswith("chatcmpl-mock-")
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)
    assert all(isinstance(chunk["created"], int) for chunk in chunks)
    assert all(chunk["model"] == "mirror-persona-v1" for chunk in chunks)
    assert all(chunk["choices"][0]["index"] == 0 for chunk in chunks)
    assert chunks[0]["choices"] == [
        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
    ]
    assert "".join(
        chunk["choices"][0]["delta"].get("content", "") for chunk in chunks
    ) == "That sounds like a lot to carry. What feels most pressing right now?"
    assert chunks[-1]["choices"] == [
        {"index": 0, "delta": {}, "finish_reason": "stop"}
    ]


@pytest.mark.anyio
async def test_chat_completion_rejects_empty_messages(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "mirror-persona-v1", "messages": []},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_metrics_exposes_mock_request_counter(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        completion_response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mirror-persona-v1",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        response = await client.get("/metrics")

    assert completion_response.status_code == 200
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "mirror_llm_mock_requests_total 1" in response.text


@pytest.mark.anyio
async def test_request_id_is_preserved_on_mock_responses(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")

    from app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health", headers={"X-Request-ID": "m2-10-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "m2-10-test"
