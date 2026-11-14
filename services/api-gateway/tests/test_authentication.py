from pathlib import Path
from typing import Self

import bcrypt
import pytest
from fastapi import HTTPException

from app.auth import (
    AuthenticatedUser,
    StoredUser,
    authenticate_user,
    get_user_lookup,
    login_client_ip,
    require_clinician,
)
from app.config import Settings


class FakeUsers:
    def __init__(self, user: StoredUser | None) -> None:
        self.user = user
        self.queried_email: str | None = None

    async def by_email(self, email: str) -> StoredUser | None:
        self.queried_email = email
        return self.user


@pytest.mark.anyio
async def test_authenticate_user_accepts_a_seeded_bcrypt_password() -> None:
    password = "mirror-demo"
    seeded = StoredUser(
        user_id="00000000-0000-0000-0000-000000000101",
        email="clinician.ada@example.test",
        role="clinician",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    users = FakeUsers(seeded)

    authenticated = await authenticate_user(users, "Clinician.Ada@Example.Test", password)

    assert authenticated == AuthenticatedUser(
        user_id=seeded.user_id, email=seeded.email, role="clinician"
    )
    assert users.queried_email == "clinician.ada@example.test"


@pytest.mark.anyio
async def test_authenticate_user_returns_none_for_unknown_user_or_wrong_password() -> None:
    seeded = StoredUser(
        user_id="00000000-0000-0000-0000-000000000201",
        email="patient.alex@example.test",
        role="patient",
        password_hash=bcrypt.hashpw(b"mirror-demo", bcrypt.gensalt()).decode(),
    )

    assert await authenticate_user(FakeUsers(None), "nobody@example.test", "mirror-demo") is None
    assert await authenticate_user(FakeUsers(seeded), seeded.email, "wrong-password") is None


def test_unknown_user_bcrypt_cost_matches_seeded_password_hashes() -> None:
    from app.auth import _UNKNOWN_USER_PASSWORD_HASH

    seed_script = Path(__file__).parents[2] / "db" / "seed.sh"

    assert _UNKNOWN_USER_PASSWORD_HASH.split(b"$")[2] == b"12"
    assert "gen_salt('bf', 12)" in seed_script.read_text()


@pytest.mark.anyio
async def test_authenticate_user_runs_bcrypt_for_an_unknown_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_hashes: list[bytes] = []

    def checkpw(_: bytes, password_hash: bytes) -> bool:
        checked_hashes.append(password_hash)
        return False

    monkeypatch.setattr("app.auth.bcrypt.checkpw", checkpw)

    assert await authenticate_user(FakeUsers(None), "nobody@example.test", "password") is None
    assert len(checked_hashes) == 1


def test_login_client_ip_ignores_forwarded_header_from_an_untrusted_peer() -> None:
    assert login_client_ip("198.51.100.10", "203.0.113.8", ["10.0.0.0/8"]) == "198.51.100.10"


def test_login_client_ip_uses_rightmost_untrusted_forwarded_hop_from_trusted_proxy() -> None:
    assert (
        login_client_ip(
            "10.0.0.5",
            "203.0.113.8, 198.51.100.10",
            ["10.0.0.0/8"],
        )
        == "198.51.100.10"
    )


def test_require_clinician_allows_only_clinician_users() -> None:
    clinician = AuthenticatedUser(
        user_id="00000000-0000-0000-0000-000000000101",
        email="clinician.ada@example.test",
        role="clinician",
    )
    patient = clinician.model_copy(update={"role": "patient"})

    assert require_clinician(clinician) == clinician
    with pytest.raises(HTTPException, match="Clinicians only") as error:
        require_clinician(patient)
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_user_lookup_uses_the_shared_database_url_with_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cursor:
        def __init__(self) -> None:
            self.query: str | None = None
            self.params: tuple[str, ...] | None = None

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: tuple[str, ...]) -> None:
            self.query = query
            self.params = params

        def fetchone(self) -> tuple[str, str, str, str]:
            return (
                "00000000-0000-0000-0000-000000000201",
                "patient.alex@example.test",
                "patient",
                "bcrypt-hash",
            )

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()
            self.closed = False

        def cursor(self) -> "Cursor":
            return self.cursor_instance

        def close(self) -> None:
            self.closed = True

    connection = Connection()
    seen_dsns: list[str] = []
    dsn = "postgresql://shared-user:shared-password@db:5432/mirror"
    monkeypatch.setattr(
        "app.auth.psycopg.connect",
        lambda value: (seen_dsns.append(value), connection)[1],
    )
    settings = Settings(
        database_url=dsn,
        jwt_signing_key="unit-test-jwt-signing-key-with-adequate-length",
    )

    dependency = get_user_lookup(settings)
    users = await anext(dependency)
    user = await users.by_email("patient.alex@example.test")
    await dependency.aclose()

    assert user is not None
    assert seen_dsns == [dsn]
    assert user.user_id == "00000000-0000-0000-0000-000000000201"
    assert connection.cursor_instance.params == ("patient.alex@example.test",)
    assert connection.closed
