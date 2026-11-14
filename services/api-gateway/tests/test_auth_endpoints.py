import bcrypt
import pytest
from app.auth import StoredUser, clear_login_attempts, get_user_lookup
from app.main import app
from httpx import ASGITransport, AsyncClient


class FakeUsers:
    """In-memory stand-in for the database lookup used by authentication endpoint tests."""

    def __init__(self) -> None:
        password_hash = bcrypt.hashpw(b"test-password", bcrypt.gensalt()).decode()
        self.users = {
            "patient.alex@example.test": StoredUser(
                user_id="00000000-0000-0000-0000-000000000201",
                email="patient.alex@example.test",
                role="patient",
                password_hash=password_hash,
            ),
            "clinician.ada@example.test": StoredUser(
                user_id="00000000-0000-0000-0000-000000000101",
                email="clinician.ada@example.test",
                role="clinician",
                password_hash=password_hash,
            ),
        }

    async def by_email(self, email: str) -> StoredUser | None:
        return self.users.get(email)


@pytest.fixture(autouse=True)
def replace_database_lookup() -> None:
    """Keep endpoint tests deterministic while production obtains users from Postgres."""
    app.dependency_overrides[get_user_lookup] = lambda: FakeUsers()
    clear_login_attempts()
    yield
    app.dependency_overrides.clear()
    clear_login_attempts()


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_login_issues_a_signed_token_for_the_database_user() -> None:
    async with client() as api:
        response = await api.post(
            "/auth/login",
            json={"email": "patient.alex@example.test", "password": "test-password"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "patient"
    assert body["user_id"] == "00000000-0000-0000-0000-000000000201"
    assert body["access_token"].count(".") == 2


@pytest.mark.anyio
async def test_refresh_renews_a_still_valid_authenticated_token() -> None:
    async with client() as api:
        login = await api.post(
            "/auth/login",
            json={"email": "patient.alex@example.test", "password": "test-password"},
        )
        refreshed = await api.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert refreshed.status_code == 200
    assert refreshed.json()["role"] == "patient"
    assert refreshed.json()["user_id"] == "00000000-0000-0000-0000-000000000201"
    assert refreshed.json()["access_token"].count(".") == 2


@pytest.mark.anyio
async def test_refresh_rejects_missing_and_expired_tokens() -> None:
    from datetime import UTC, datetime, timedelta

    from app.auth import AuthenticatedUser, issue_access_token
    from app.config import get_settings

    expired = issue_access_token(
        AuthenticatedUser(
            user_id="00000000-0000-0000-0000-000000000201",
            email="patient.alex@example.test",
            role="patient",
        ),
        signing_key=get_settings().jwt_signing_key,
        now=datetime.now(UTC) - timedelta(minutes=2),
        expires_in=timedelta(minutes=1),
    )
    async with client() as api:
        missing = await api.post("/auth/refresh")
        expired_response = await api.post(
            "/auth/refresh", headers={"Authorization": f"Bearer {expired}"}
        )

    assert missing.status_code == 401
    assert expired_response.status_code == 401


@pytest.mark.anyio
async def test_patient_endpoint_accepts_patient_jwt_and_rejects_clinician_jwt() -> None:
    async with client() as api:
        patient_login = await api.post(
            "/auth/login",
            json={"email": "patient.alex@example.test", "password": "test-password"},
        )
        clinician_login = await api.post(
            "/auth/login",
            json={"email": "clinician.ada@example.test", "password": "test-password"},
        )
        patient = await api.post(
            "/sessions",
            json={"camera_consent": False},
            headers={"Authorization": f"Bearer {patient_login.json()['access_token']}"},
        )
        clinician = await api.post(
            "/sessions",
            json={"camera_consent": False},
            headers={"Authorization": f"Bearer {clinician_login.json()['access_token']}"},
        )

    assert patient.status_code == 201
    assert clinician.status_code == 403


@pytest.mark.anyio
async def test_login_throttles_repeated_failures_without_disclosing_account_state() -> None:
    async with client() as api:
        responses = [
            await api.post(
                "/auth/login",
                json={
                    "email": "patient.alex@example.test",
                    "password": "wrong-password",
                },
            )
            for _ in range(6)
        ]

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429


@pytest.mark.anyio
async def test_successful_login_clears_prior_failed_attempts() -> None:
    async with client() as api:
        failures = [
            await api.post(
                "/auth/login",
                json={
                    "email": "patient.alex@example.test",
                    "password": "wrong-password",
                },
            )
            for _ in range(4)
        ]
        success = await api.post(
            "/auth/login",
            json={"email": "patient.alex@example.test", "password": "test-password"},
        )
        next_failure = await api.post(
            "/auth/login",
            json={
                "email": "patient.alex@example.test",
                "password": "wrong-password",
            },
        )

    assert [response.status_code for response in failures] == [401] * 4
    assert success.status_code == 200
    assert next_failure.status_code == 401
