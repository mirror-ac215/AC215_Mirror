from datetime import UTC, datetime, timedelta

import pytest

from app.auth import AuthenticatedUser, decode_access_token, issue_access_token


@pytest.mark.parametrize("role", ["patient", "clinician"])
def test_signed_access_token_round_trips_the_seeded_user_identity_and_role(
    role: str,
) -> None:
    user = AuthenticatedUser(
        user_id="00000000-0000-0000-0000-000000000101",
        email="clinician.ada@example.test",
        role=role,
    )

    token = issue_access_token(user, signing_key="unit-test-signing-key-with-adequate-length")

    assert (
        decode_access_token(token, signing_key="unit-test-signing-key-with-adequate-length") == user
    )


def test_tampered_access_token_is_rejected() -> None:
    user = AuthenticatedUser(
        user_id="00000000-0000-0000-0000-000000000201",
        email="patient.alex@example.test",
        role="patient",
    )
    token = issue_access_token(user, signing_key="unit-test-signing-key-with-adequate-length")

    with pytest.raises(ValueError, match="Invalid token"):
        decode_access_token(token + "x", signing_key="unit-test-signing-key-with-adequate-length")


def test_expired_access_token_is_rejected() -> None:
    user = AuthenticatedUser(
        user_id="00000000-0000-0000-0000-000000000201",
        email="patient.alex@example.test",
        role="patient",
    )
    token = issue_access_token(
        user,
        signing_key="unit-test-signing-key-with-adequate-length",
        now=datetime.now(UTC) - timedelta(minutes=2),
        expires_in=timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="expired"):
        decode_access_token(token, signing_key="unit-test-signing-key-with-adequate-length")
