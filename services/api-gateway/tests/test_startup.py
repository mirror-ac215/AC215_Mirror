import pytest
from app import main
from app.text_emotion import TextEmotionUnavailable


@pytest.mark.anyio
async def test_gateway_warms_text_emotion_model_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Emotion:
        def warm_up(self) -> None:
            calls.append("warm")

    monkeypatch.setattr(main, "get_text_emotion", lambda: Emotion())

    async with main.app.router.lifespan_context(main.app):
        assert calls == ["warm"]


@pytest.mark.anyio
async def test_gateway_stays_available_when_startup_warmup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> None:
        raise TextEmotionUnavailable("model unavailable")

    monkeypatch.setattr(
        main,
        "get_text_emotion",
        lambda: type("Emotion", (), {"warm_up": lambda self: unavailable()})(),
    )

    async with main.app.router.lifespan_context(main.app):
        pass
