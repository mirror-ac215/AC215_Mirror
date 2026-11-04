"""PostgreSQL-compatible persistence for gateway chat turns."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, Self


class Cursor(Protocol):
    def execute(self, query: str, params: tuple[Any, ...]) -> Any: ...

    def fetchone(self) -> tuple[str]: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


class InMemoryRepository:
    """Ephemeral adapter for isolated tests only; production uses PostgresRepository."""

    def __init__(self) -> None:
        self.sessions: list[dict] = []
        self.messages: list[dict] = []
        self.windows: list[dict] = []
        self.flags: list[dict] = []

    async def add_session(
        self, session_id: str, patient_id: str, started_at: datetime, camera_consent: bool
    ) -> None:
        self.sessions.append(
            {
                "id": session_id,
                "patient_id": patient_id,
                "started_at": started_at,
                "camera_consent": camera_consent,
            }
        )

    async def add_message(
        self, session_id: str, role: str, text: str, safety_hit: bool
    ) -> str:
        message_id = f"memory-message-{len(self.messages) + 1}"
        self.messages.append(
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "text": text,
                "safety_hit": safety_hit,
            }
        )
        return message_id

    async def add_emotion_window(self, session_id: str, context: dict) -> None:
        self.windows.append({"session_id": session_id, "context": context})

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        self.flags.append({"patient_id": patient_id, "message_id": message_id})


class PostgresRepository:
    """Small DB-API adapter using PostgreSQL's native ``%s`` parameter style.

    A fresh connection per operation keeps the web process concurrency-safe and
    makes the class work with psycopg as well as fake DB-API connections.
    """

    def __init__(self, connect: Callable[[], Connection]) -> None:
        self._connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgresRepository:
        def connect() -> Connection:
            import psycopg

            return psycopg.connect(dsn)

        return cls(connect)

    async def add_session(
        self, session_id: str, patient_id: str, started_at: datetime, camera_consent: bool
    ) -> None:
        await asyncio.to_thread(
            self._execute,
            """INSERT INTO sessions (id, patient_id, started_at, camera_consent)
               VALUES (%s, %s, %s, %s)""",
            (session_id, patient_id, started_at, camera_consent),
        )

    async def add_message(
        self, session_id: str, role: str, text: str, safety_hit: bool
    ) -> str:
        return await asyncio.to_thread(
            self._insert_returning_id,
            "INSERT INTO messages (session_id, role, text, safety_hit) VALUES (%s, %s, %s, %s) RETURNING id",
            (session_id, role, text, safety_hit),
        )

    async def add_emotion_window(self, session_id: str, context: dict) -> None:
        visual = context["visual"]
        await asyncio.to_thread(
            self._execute,
            """INSERT INTO emotion_windows (session_id, visual_status, visual_top2, text_top2, tone_mode)
               VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)""",
            (
                session_id,
                visual["status"],
                self._json(visual.get("top2")),
                self._json(context["text"]["top2"]),
                context["tone_mode"],
            ),
        )

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        await asyncio.to_thread(
            self._execute,
            "INSERT INTO review_flags (patient_id, message_id) VALUES (%s, %s)",
            (patient_id, message_id),
        )

    @staticmethod
    def _json(value: object) -> str | None:
        import json

        return json.dumps(value) if value is not None else None

    def _insert_returning_id(self, query: str, params: tuple[Any, ...]) -> str:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
            connection.commit()
            if row is None:
                raise RuntimeError("Postgres did not return an inserted message id")
            return str(row[0])
        finally:
            connection.close()

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
            connection.commit()
        finally:
            connection.close()
