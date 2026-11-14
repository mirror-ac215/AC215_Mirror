"""M4-03 clinician API authorization and ownership behavior."""

from collections.abc import Generator
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.clinician import get_clinician_repository
from app.main import app
from app.schemas import PatientSummary, ReviewFlagSummary, TrendPoint
from tests.conftest import auth_headers

ADA_ID = "00000000-0000-0000-0000-000000000101"
LUIS_ID = "00000000-0000-0000-0000-000000000102"
ALEX_ID = "00000000-0000-0000-0000-000000000201"
FLAG_ALEX_ID = "00000000-0000-0000-0000-000000000301"

CLINICIAN_ADA = auth_headers(ADA_ID, "clinician.ada@example.test", "clinician")
CLINICIAN_LUIS = auth_headers(LUIS_ID, "clinician.luis@example.test", "clinician")
PATIENT_ALEX = auth_headers(ALEX_ID, "patient.alex@example.test", "patient")


class FakeClinicianRepository:
    """A deterministic clinician-owned aggregate read model for endpoint tests."""

    def __init__(self) -> None:
        self.reviewed_flags: list[tuple[str, str]] = []

    async def list_patients(self, clinician_id: str) -> list[PatientSummary]:
        assert clinician_id == ADA_ID
        return [
            PatientSummary(
                patient_id=ALEX_ID,
                display_name="Alex Rivera",
                last_session_at=datetime.fromisoformat("2026-11-09T08:00:00+00:00"),
                needs_review=True,
            )
        ]

    async def patient_trend(
        self, clinician_id: str, patient_id: str
    ) -> list[TrendPoint] | None:
        if clinician_id != ADA_ID or patient_id != ALEX_ID:
            return None
        return [
            TrendPoint(
                ts=datetime.fromisoformat("2026-11-09T08:00:00+00:00"),
                visual_status="camera_off",
                visual_top2=None,
                text_top2=[("neutral", 1.0)],
                tone_mode="supportive",
            )
        ]

    async def review_flags(
        self, clinician_id: str, patient_id: str
    ) -> list[ReviewFlagSummary] | None:
        if clinician_id != ADA_ID or patient_id != ALEX_ID:
            return None
        return [
            ReviewFlagSummary(
                flag_id=FLAG_ALEX_ID,
                created_at=datetime.fromisoformat("2026-11-09T08:00:00+00:00"),
                reviewed_at=None,
            )
        ]

    async def mark_reviewed(self, clinician_id: str, flag_id: str) -> bool:
        if clinician_id != ADA_ID or flag_id != FLAG_ALEX_ID:
            return False
        self.reviewed_flags.append((clinician_id, flag_id))
        return True


@pytest.fixture(autouse=True)
def replace_clinician_repository() -> Generator[None, None, None]:
    repository = FakeClinicianRepository()
    app.dependency_overrides[get_clinician_repository] = lambda: repository
    yield
    app.dependency_overrides.pop(get_clinician_repository, None)


def test_trend_point_rejects_unstructured_or_out_of_range_aggregate_values() -> None:
    base = {
        "ts": "2026-11-09T08:00:00+00:00",
        "visual_status": "ok",
        "text_top2": [["neutral", 0.9]],
        "tone_mode": "supportive",
    }

    with pytest.raises(ValidationError):
        TrendPoint.model_validate({**base, "visual_top2": [["patient message", 0.5, "extra"]]})
    with pytest.raises(ValidationError):
        TrendPoint.model_validate({**base, "visual_top2": [["neutral", 1.1]]})
    with pytest.raises(ValidationError):
        TrendPoint.model_validate({**base, "visual_top2": [["message_fragment", 0.5]]})

    stored_text_label = TrendPoint.model_validate(
        {**base, "visual_top2": None, "text_top2": [["joy", 0.9]]}
    )
    assert stored_text_label.text_top2 == [("joy", 0.9)]


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_clinician_can_list_only_their_patients() -> None:
    async with client() as api:
        response = await api.get("/clinician/patients", headers=CLINICIAN_ADA)

    assert response.status_code == 200
    assert response.json() == [
        {
            "patient_id": ALEX_ID,
            "display_name": "Alex Rivera",
            "last_session_at": "2026-11-09T08:00:00Z",
            "needs_review": True,
        }
    ]


@pytest.mark.anyio
async def test_patient_cannot_list_clinician_patients() -> None:
    async with client() as api:
        response = await api.get("/clinician/patients", headers=PATIENT_ALEX)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_assigned_clinician_can_read_only_aggregate_trend() -> None:
    async with client() as api:
        response = await api.get(
            f"/clinician/patients/{ALEX_ID}/trend", headers=CLINICIAN_ADA
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "ts": "2026-11-09T08:00:00Z",
            "visual_status": "camera_off",
            "visual_top2": None,
            "text_top2": [["neutral", 1.0]],
            "tone_mode": "supportive",
        }
    ]
    assert "patient message" not in response.text
    assert "session_id" not in response.text


@pytest.mark.anyio
async def test_unassigned_clinician_cannot_read_patient_trend() -> None:
    async with client() as api:
        response = await api.get(
            f"/clinician/patients/{ALEX_ID}/trend", headers=CLINICIAN_LUIS
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_assigned_clinician_can_list_flag_metadata_without_message_text() -> None:
    async with client() as api:
        response = await api.get(
            f"/clinician/patients/{ALEX_ID}/review-flags", headers=CLINICIAN_ADA
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "flag_id": FLAG_ALEX_ID,
            "created_at": "2026-11-09T08:00:00Z",
            "reviewed_at": None,
        }
    ]
    assert "message" not in response.text


@pytest.mark.anyio
async def test_unassigned_clinician_cannot_list_patient_review_flags() -> None:
    async with client() as api:
        response = await api.get(
            f"/clinician/patients/{ALEX_ID}/review-flags", headers=CLINICIAN_LUIS
        )

    assert response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("GET", "/clinician/patients/not-a-uuid/trend", None),
        ("GET", "/clinician/patients/not-a-uuid/review-flags", None),
        ("PATCH", "/clinician/review-flags/not-a-uuid", {"reviewed": True}),
    ],
)
async def test_malformed_clinician_resource_ids_return_422(
    method: str, path: str, json: dict[str, bool] | None
) -> None:
    async with client() as api:
        response = await api.request(method, path, json=json, headers=CLINICIAN_ADA)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_assigned_clinician_can_mark_only_their_unresolved_flag_reviewed() -> (
    None
):
    async with client() as api:
        updated = await api.patch(
            f"/clinician/review-flags/{FLAG_ALEX_ID}",
            json={"reviewed": True},
            headers=CLINICIAN_ADA,
        )
        forbidden = await api.patch(
            f"/clinician/review-flags/{FLAG_ALEX_ID}",
            json={"reviewed": True},
            headers=CLINICIAN_LUIS,
        )

    assert updated.status_code == 200
    assert updated.json() == {"reviewed": True}
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_review_flag_endpoint_rejects_any_state_other_than_reviewed() -> None:
    async with client() as api:
        response = await api.patch(
            f"/clinician/review-flags/{FLAG_ALEX_ID}",
            json={"reviewed": False},
            headers=CLINICIAN_ADA,
        )

    assert response.status_code == 422
