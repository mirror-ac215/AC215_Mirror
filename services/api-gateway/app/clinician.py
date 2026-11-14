"""M4-03 clinician-only patient summaries, trends, and review updates."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, Any, Protocol, Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthenticatedUser, require_clinician
from app.config import Settings, get_settings
from app.schemas import (
    PatientSummary,
    ReviewFlagAcknowledgement,
    ReviewFlagSummary,
    ReviewFlagUpdate,
    TrendPoint,
)

router = APIRouter(prefix="/clinician", tags=["clinician"])


class Cursor(Protocol):
    """Small synchronous DB-API surface used by the repository adapter."""

    def execute(self, query: str, params: tuple[Any, ...]) -> Any: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


class Connection(Protocol):
    """Transaction boundary required by clinician read and update operations."""

    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


class ClinicianRepository(Protocol):
    """Read and update only data scoped by a clinician-patient assignment."""

    async def list_patients(self, clinician_id: str) -> list[PatientSummary]: ...

    async def patient_trend(
        self, clinician_id: str, patient_id: str
    ) -> list[TrendPoint] | None: ...

    async def review_flags(
        self, clinician_id: str, patient_id: str
    ) -> list[ReviewFlagSummary] | None: ...

    async def mark_reviewed(self, clinician_id: str, flag_id: str) -> bool: ...


class PostgresClinicianRepository:
    """PostgreSQL adapter that enforces ownership in every query boundary."""

    def __init__(self, connect: Callable[[], Connection]) -> None:
        self._connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgresClinicianRepository:
        def connect() -> Connection:
            import psycopg

            return psycopg.connect(dsn)

        return cls(connect)

    async def list_patients(self, clinician_id: str) -> list[PatientSummary]:
        rows = await asyncio.to_thread(
            self._fetchall,
            """SELECT p.user_id::text, u.display_name, MAX(s.started_at),
                      EXISTS (
                          SELECT 1 FROM review_flags rf
                          WHERE rf.patient_id = p.user_id AND rf.reviewed_at IS NULL
                      )
                 FROM patients p
                 JOIN users u ON u.id = p.user_id
                 LEFT JOIN sessions s ON s.patient_id = p.user_id
                 WHERE p.clinician_id = %s
                 GROUP BY p.user_id, u.display_name
                 ORDER BY u.display_name""",
            (clinician_id,),
        )
        return [
            PatientSummary(
                patient_id=str(patient_id),
                display_name=display_name,
                last_session_at=last_session_at,
                needs_review=needs_review,
            )
            for patient_id, display_name, last_session_at, needs_review in rows
        ]

    async def patient_trend(self, clinician_id: str, patient_id: str) -> list[TrendPoint] | None:
        """Return a trend only when the assignment matches in the same SQL query."""
        rows = await asyncio.to_thread(
            self._fetchall,
            """SELECT ew.ts, ew.visual_status::text, ew.visual_top2, ew.text_top2, ew.tone_mode::text
                 FROM patients p
                 LEFT JOIN sessions s ON s.patient_id = p.user_id
                 LEFT JOIN emotion_windows ew ON ew.session_id = s.id
                 WHERE p.clinician_id = %s AND p.user_id = %s
                 ORDER BY ew.ts""",
            (clinician_id, patient_id),
        )
        if not rows:
            return None
        return [
            TrendPoint(
                ts=ts,
                visual_status=visual_status,
                visual_top2=visual_top2,
                text_top2=text_top2,
                tone_mode=tone_mode,
            )
            for ts, visual_status, visual_top2, text_top2, tone_mode in rows
            if ts is not None
        ]

    async def review_flags(
        self, clinician_id: str, patient_id: str
    ) -> list[ReviewFlagSummary] | None:
        """Return flag metadata only when assignment matches in this SQL query."""
        rows = await asyncio.to_thread(
            self._fetchall,
            """SELECT rf.id::text, rf.created_at, rf.reviewed_at
                 FROM patients p
                 LEFT JOIN review_flags rf ON rf.patient_id = p.user_id
                 WHERE p.clinician_id = %s AND p.user_id = %s
                 ORDER BY rf.created_at DESC NULLS LAST""",
            (clinician_id, patient_id),
        )
        if not rows:
            return None
        return [
            ReviewFlagSummary(flag_id=flag_id, created_at=created_at, reviewed_at=reviewed_at)
            for flag_id, created_at, reviewed_at in rows
            if flag_id is not None
        ]

    async def mark_reviewed(self, clinician_id: str, flag_id: str) -> bool:
        row = await asyncio.to_thread(
            self._fetchone_and_commit,
            """UPDATE review_flags rf
                 SET reviewed_at = now(), reviewed_by = %s
                 FROM patients p
                 WHERE rf.id = %s
                   AND rf.patient_id = p.user_id
                   AND p.clinician_id = %s
                   AND rf.reviewed_at IS NULL
                 RETURNING rf.id""",
            (clinician_id, flag_id, clinician_id),
        )
        return row is not None

    def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        finally:
            connection.close()

    def _fetchone(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        finally:
            connection.close()

    def _fetchone_and_commit(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
            connection.commit()
            return row
        finally:
            connection.close()


def get_clinician_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClinicianRepository:
    """Construct a database adapter from the service's shared configured DSN."""
    return PostgresClinicianRepository.from_dsn(settings.database_url)


@router.get(
    "/patients",
    response_model=list[PatientSummary],
    responses={
        200: {"description": "Patient list"},
        401: {"description": "Not logged in or token is invalid"},
        403: {"description": "Not a clinician"},
    },
)
async def list_patients(
    user: Annotated[AuthenticatedUser, Depends(require_clinician)],
    repository: Annotated[ClinicianRepository, Depends(get_clinician_repository)],
) -> list[PatientSummary]:
    """Return only the authenticated clinician's assigned patient summaries."""
    return await repository.list_patients(user.user_id)


@router.get(
    "/patients/{patient_id}/trend",
    response_model=list[TrendPoint],
    responses={
        200: {"description": "One point per stored emotion window"},
        401: {"description": "Not logged in or token is invalid"},
        403: {"description": "Not this clinician's patient"},
    },
)
async def patient_trend(
    patient_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_clinician)],
    repository: Annotated[ClinicianRepository, Depends(get_clinician_repository)],
) -> list[TrendPoint]:
    """Return aggregate trend windows only after clinician ownership is confirmed."""
    trend = await repository.patient_trend(user.user_id, str(patient_id))
    if trend is None:
        raise HTTPException(status_code=403, detail="Not this clinician's patient")
    return trend


@router.get(
    "/patients/{patient_id}/review-flags",
    response_model=list[ReviewFlagSummary],
    responses={
        200: {"description": "Clinician-owned review flag metadata"},
        401: {"description": "Not logged in or token is invalid"},
        403: {"description": "Not this clinician's patient"},
    },
)
async def list_patient_review_flags(
    patient_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_clinician)],
    repository: Annotated[ClinicianRepository, Depends(get_clinician_repository)],
) -> list[ReviewFlagSummary]:
    """Return flag IDs and timestamps, never messages, for one assigned patient."""
    flags = await repository.review_flags(user.user_id, str(patient_id))
    if flags is None:
        raise HTTPException(status_code=403, detail="Not this clinician's patient")
    return flags


@router.patch(
    "/review-flags/{flag_id}",
    response_model=ReviewFlagAcknowledgement,
    responses={
        200: {"description": "Flag marked as reviewed"},
        401: {"description": "Not logged in or token is invalid"},
        403: {"description": "Not this clinician's patient"},
    },
)
async def mark_review_flag_reviewed(
    flag_id: UUID,
    _: ReviewFlagUpdate,
    user: Annotated[AuthenticatedUser, Depends(require_clinician)],
    repository: Annotated[ClinicianRepository, Depends(get_clinician_repository)],
) -> ReviewFlagAcknowledgement:
    """Mark one assigned patient's unresolved review flag as reviewed."""
    if not await repository.mark_reviewed(user.user_id, str(flag_id)):
        raise HTTPException(status_code=403, detail="Not this clinician's unresolved review flag")
    return ReviewFlagAcknowledgement(reviewed=True)
