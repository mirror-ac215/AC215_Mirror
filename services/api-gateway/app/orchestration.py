"""Gateway turn orchestration and injectable outbound service contracts."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from app import metrics, safety
from app.crisis_meaning import CrisisMeaning, CrisisMeaningUnavailable
from app.fusion import TurnHistory, fuse
from app.prompt import build_messages
from app.text_emotion import TextEmotion, TextEmotionUnavailable

logger = logging.getLogger("mirror")


def main_signal(context: dict) -> str:
    """The fixed signal label embedded in fusion's human-readable note."""
    note = context["note"]
    if note.startswith("main signal: face"):
        return "face"
    if note.startswith("main signal: text"):
        return "text"
    return "none"


# Sent instead when a reply after a question is nothing but questions.
QUESTION_FALLBACK = "I'm here, and I'm listening."


# M4-04: the gentle reply when the language model times out or fails before saying anything.
# No question (the reply rules allow one at most) and no 988: this is not a crisis turn.
LLM_FALLBACK_REPLY = (
    "I'm having trouble finding my words right now, but I read what you wrote. "
    "You're welcome to keep writing, or to try again in a moment."
)
# Added when the model fails part-way, so the reply never just stops mid-sentence.
LLM_INTERRUPTED_NOTE = " (Sorry, I lost my train of thought there. You can keep writing.)"


def drop_questions(reply: str) -> str:
    """Removes every sentence with a question mark; QUESTION_FALLBACK if nothing is left."""
    sentences = re.findall(r"[^.!?]*[.!?]+[\"')\]]*|[^.!?]+$", reply)
    kept = "".join(s for s in sentences if "?" not in s).strip()
    return kept or QUESTION_FALLBACK


class TurnRepository(Protocol):
    async def add_message(self, session_id: str, role: str, text: str, safety_hit: bool) -> str: ...

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
    safety_kind: str | None = None
    # Ends the turn's check-in reservation if the reply never got recorded (M4-17). Safe to call
    # more than once, and also when `tokens` was never started: the chat endpoint calls it when
    # its response ends, however it ends.
    close: Callable[[], None] = lambda: None


class ChatOrchestrator:
    """Safety-first path for one patient turn.

    The repository and LLM are protocols on purpose: HTTP and PostgreSQL are
    production adapters, while integration tests use deterministic fakes.
    """

    def __init__(
        self,
        repository: TurnRepository,
        llm: LLMClient,
        text_emotion: TextEmotion,
        crisis_meaning: CrisisMeaning | None = None,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._text_emotion = text_emotion
        self._crisis_meaning = crisis_meaning

    def _safety(self, text: str) -> safety.SafetyResult:
        """Rules first (M3-07); if they don't say crisis, the meaning layer (M4-15).

        Either one firing means crisis, also over a medication or camera hit:
        crisis always wins. If the model failed to load or cannot score this message,
        the deterministic rules decide alone and the fallback is counted and logged.
        """
        result = safety.check(text)
        if result.kind == "crisis" or self._crisis_meaning is None:
            return result
        try:
            rule_id = self._crisis_meaning.check(text)
        except CrisisMeaningUnavailable as exc:
            # Visible, never silent: one count per message checked by the rules alone,
            # and a structured log with the stage (never the message text).
            metrics.record_fallback("crisis_meaning_unavailable")
            logger.warning("crisis_meaning_fallback", extra={"stage": exc.stage})
            return result
        return safety.SafetyResult("crisis", rule_id) if rule_id else result

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
        safety_result = self._safety(text)
        if safety_result.kind == "crisis":

            async def no_tokens() -> AsyncIterator[str]:
                if False:
                    yield ""

            try:
                patient_message_id = await self._repository.add_message(
                    session_id, "patient", text, True
                )
                await self._repository.add_review_flag(patient_id, patient_message_id)
            except Exception as exc:  # noqa: BLE001 -- crisis resources must survive any DB failure
                # Do not make emergency resources depend on database availability,
                # and never put patient text in logs.
                logger.error("crisis_persistence_failed type=%s", type(exc).__name__)
                return ChatTurn(
                    message_id="",
                    context=None,
                    tokens=no_tokens(),
                    crisis=safety.crisis_payload(review_flag_created=False),
                    safety_rule=safety_result.rule_id,
                )

            return ChatTurn(
                message_id=patient_message_id,
                context=None,
                tokens=no_tokens(),
                crisis=safety.crisis_payload(review_flag_created=True),
                safety_rule=safety_result.rule_id,
            )

        patient_message_id = await self._repository.add_message(session_id, "patient", text, False)

        try:
            text_context = self._text_emotion.analyse(text).as_context()
        except TextEmotionUnavailable:
            text_context = None
        context = fuse(visual, text_context, history)
        metrics.record_gate(context["visual"]["status"])
        metrics.record_fusion(context["agreement"], context["tone_mode"], main_signal(context))
        llm_messages = build_messages(context, text, conversation)
        fixed_text = {
            "medication": safety.MEDICATION_REPLY,
            "camera": safety.CAMERA_REPLY,
        }.get(safety_result.kind or "")

        async def fixed_reply() -> AsyncIterator[str]:
            yield fixed_text

        # Never two questions in a row. Only the turn after a question is held back,
        # because its questions can only be removed once the whole reply has arrived.
        previous = next(
            (m["content"] for m in reversed(conversation) if m["role"] == "assistant"), ""
        )
        hold_reply = not fixed_text and "?" in previous

        reserved = context["agreement"] == "disagree"
        turn_open = True

        def close() -> None:
            # Client left (before or during the reply) or saving failed: free the check-in.
            nonlocal turn_open
            if turn_open and reserved:
                history.release_check_in()
            turn_open = False

        async def forward_and_persist() -> AsyncIterator[str]:
            try:
                async for token in stream_and_save():
                    yield token
            finally:
                close()

        async def stream_and_save() -> AsyncIterator[str]:
            reply_parts: list[str] = []
            llm_failed = False
            # Medication and camera questions never reach the LLM: same stream, fixed text.
            source = fixed_reply() if fixed_text else self._llm.stream(llm_messages)
            try:
                async for token in source:
                    reply_parts.append(token)
                    if not hold_reply:
                        yield token
            except Exception as exc:  # noqa: BLE001 -- any LLM failure falls back (M4-04)
                # Timeout, connection refused, bad stream: the turn still ends with a reply,
                # a done event and a saved message. Never log the patient's text.
                logger.warning("llm_fallback type=%s", type(exc).__name__)
                metrics.record_fallback("llm_unavailable")
                llm_failed = True
                note = LLM_INTERRUPTED_NOTE if reply_parts else LLM_FALLBACK_REPLY
                reply_parts.append(note)
                if not hold_reply:
                    yield note
            reply = "".join(reply_parts)
            cut = False
            if hold_reply:
                kept = drop_questions(reply)
                cut = kept != reply.strip()
                reply = kept
                yield reply
            await self._repository.add_message(session_id, "assistant", reply, False)
            await self._repository.add_emotion_window(session_id, context)
            # M4-17: a check-in only counts if the patient saw the model's reply as written.
            # A fixed reply, an LLM fallback or a removed question means it never reached them.
            history.record(context, reply_delivered=not (fixed_text or llm_failed or cut))
            nonlocal turn_open
            turn_open = False  # recorded: the reservation is settled, close() has nothing to do

        # No await since fuse(), so no other turn of this session has run in between: reserving
        # here means an overlapping turn cannot check in as well (M4-17).
        if reserved:
            history.reserve_check_in()
        return ChatTurn(
            message_id=patient_message_id,
            context=context,
            tokens=forward_and_persist(),
            safety_rule=safety_result.rule_id,
            safety_kind=safety_result.kind,
            close=close,
        )
