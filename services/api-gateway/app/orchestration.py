"""Gateway turn orchestration and injectable outbound service contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app import safety
from app.fusion import TurnHistory, fuse
from app.prompt import build_messages
from app.text_emotion import TextEmotion, TextEmotionUnavailable


class TurnRepository(Protocol):
    async def add_message(
        self, session_id: str, role: str, text: str, safety_hit: bool
    ) -> str: ...

    async def add_emotion_window(self, session_id: str, context: dict) -> None: ...

    async def add_review_flag(self, patient_id: str, message_id: str) -> None: ...


class LLMClient(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


@dataclass
class ChatTurn:
    message_id: str
    context: dict | None
    tokens: AsyncIterator[str]
    crisis: dict | None = None
    safety_rule: str | None = None


class ChatOrchestrator:
    """Safety-first path for one patient turn.

    The repository and LLM are protocols on purpose: HTTP and PostgreSQL are
    production adapters, while integration tests use deterministic fakes.
    """

    def __init__(
        self, repository: TurnRepository, llm: LLMClient, text_emotion: TextEmotion
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._text_emotion = text_emotion

    async def start_turn(
        self,
        *,
        session_id: str,
        patient_id: str,
        text: str,
        visual: dict,
        history: TurnHistory,
        conversation: list[dict[str, str]],
    ) -> ChatTurn:
        safety_result = safety.check(text)
        patient_message_id = await self._repository.add_message(
            session_id, "patient", text, safety_result.hit
        )
        if safety_result.kind == "crisis":
            await self._repository.add_review_flag(patient_id, patient_message_id)

            async def no_tokens() -> AsyncIterator[str]:
                if False:
                    yield ""

            return ChatTurn(
                message_id=patient_message_id,
                context=None,
                tokens=no_tokens(),
                crisis=safety.crisis_payload(review_flag_created=True),
                safety_rule=safety_result.rule_id,
            )

        try:
            text_context = self._text_emotion.analyse(text).as_context()
        except TextEmotionUnavailable:
            text_context = None
        context = fuse(visual, text_context, history)
        llm_messages = build_messages(context, text, conversation)

        async def forward_and_persist() -> AsyncIterator[str]:
            reply_parts: list[str] = []
            async for token in self._llm.stream(llm_messages):
                reply_parts.append(token)
                yield token
            reply = "".join(reply_parts)
            await self._repository.add_message(session_id, "assistant", reply, False)
            await self._repository.add_emotion_window(session_id, context)
            history.record(context)

        return ChatTurn(
            message_id=patient_message_id,
            context=context,
            tokens=forward_and_persist(),
        )
