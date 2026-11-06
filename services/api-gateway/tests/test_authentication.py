from typing import Self

import bcrypt
import pytest

from app.auth import AuthenticatedUser, StoredUser, authenticate_user, get_user_lookup
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

    authenticated = await authenticate_user(
        users, "Clinician.Ada@Example.Test", password
    )

    assert authenticated == AuthenticatedUser(
        user_id=seeded.user_id, email=seeded.email, role="clinician"
    )
    assert users.queried_email == "clinician.ada@example.test"


@pytest.mark.anyio
async def test_authenticate_user_returns_none_for_unknown_user_or_wrong_password() -> (
    None
):
    seeded = StoredUser(
        user_id="00000000-0000-0000-0000-000000000201",
        email="patient.alex@example.test",
        role="patient",
        password_hash=bcrypt.hashpw(b"mirror-demo", bcrypt.gensalt()).decode(),
    )

    assert (
        await authenticate_user(FakeUsers(None), "nobody@example.test", "mirror-demo")
        is None
    )
    assert (
        await authenticate_user(FakeUsers(seeded), seeded.email, "wrong-password")
        is None
    )


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
