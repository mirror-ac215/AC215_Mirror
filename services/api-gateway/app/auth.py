"""Database-backed authentication and role authorization for the API gateway."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import Annotated, Any, Protocol, cast

import bcrypt
import jwt
import psycopg
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.schemas import LoginResponse, Role


class AuthenticatedUser(BaseModel):
    """Identity carried in a verified access-token claim set."""

    user_id: str
    email: str
    role: Role


class StoredUser(AuthenticatedUser):
    """A database user with the bcrypt verifier, never returned to clients."""

    password_hash: str


# A valid bcrypt verifier with a deliberately unrelated password. It equalizes
# the expensive check for unknown accounts without representing a credential.
_UNKNOWN_USER_PASSWORD_HASH = b"$2b$12$ZPHW5dahTr8D8RFe0AFtd.639ZiyfMfhU7eN4pZXI773B628d6R.W"


class UserLookup(Protocol):
    """Minimal database boundary required to authenticate a user."""

    async def by_email(self, email: str) -> StoredUser | None: ...


class PostgresUserLookup:
    """Look up a login-capable user through a parameterized psycopg query."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def by_email(self, email: str) -> StoredUser | None:
        return await asyncio.to_thread(self._by_email, email)

    def _by_email(self, email: str) -> StoredUser | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, email, role::text, password_hash
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return StoredUser(
            user_id=str(row[0]),
            email=str(row[1]),
            role=cast(Role, str(row[2])),
            password_hash=str(row[3]),
        )


async def get_user_lookup(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[UserLookup]:
    """Yield a short-lived psycopg lookup using the shared DATABASE_URL."""
    try:
        connection = await asyncio.to_thread(psycopg.connect, settings.database_url)
    except (OSError, psycopg.Error) as error:
        raise HTTPException(
            status_code=503, detail="Authentication unavailable"
        ) from error

    try:
        yield PostgresUserLookup(connection)
    finally:
        await asyncio.to_thread(connection.close)


async def authenticate_user(
    users: UserLookup, email: str, password: str
) -> AuthenticatedUser | None:
    """Authenticate against the seeded bcrypt hash without leaking which check failed."""
    stored = await users.by_email(email.lower())
    if stored is None:
        bcrypt.checkpw(password.encode(), _UNKNOWN_USER_PASSWORD_HASH)
        return None
    try:
        valid = bcrypt.checkpw(password.encode(), stored.password_hash.encode())
    except ValueError:
        return None
    if not valid:
        return None
    return AuthenticatedUser(
        user_id=stored.user_id, email=stored.email, role=stored.role
    )


def issue_access_token(
    user: AuthenticatedUser,
    *,
    signing_key: str,
    now: datetime | None = None,
    expires_in: timedelta = timedelta(minutes=30),
) -> str:
    """Issue a short-lived, HS256-signed JWT with only authorization claims."""
    issued_at = now or datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user.user_id,
            "email": user.email,
            "role": user.role,
            "iss": "mirror-api-gateway",
            "iat": issued_at,
            "exp": issued_at + expires_in,
        },
        signing_key,
        algorithm="HS256",
    )


def decode_access_token(token: str, *, signing_key: str) -> AuthenticatedUser:
    """Verify signature, issuer, expiry, and role shape before trusting claims."""
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            issuer="mirror-api-gateway",
            options={"require": ["sub", "email", "role", "iat", "exp", "iss"]},
        )
        return AuthenticatedUser(
            user_id=claims["sub"], email=claims["email"], role=claims["role"]
        )
    except jwt.ExpiredSignatureError as error:
        raise ValueError("Access token expired") from error
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise ValueError("Invalid token") from error


bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")

# A process-local backstop against rapid credential stuffing. Deployment-scale
# rate limiting belongs at the proxy/load-balancer layer as well.
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=5)
_login_failures: dict[str, deque[datetime]] = {}


def login_throttle_key(email: str, client_host: str | None) -> str:
    """Scope failed-attempt tracking to a normalized account and client address."""
    return f"{email.lower()}:{client_host or 'unknown'}"


def login_client_ip(
    client_host: str | None,
    forwarded_for: str | None,
    trusted_proxy_ips: list[str],
) -> str | None:
    """Return a verified client IP without trusting direct-client X-Forwarded-For.

    If the direct peer is a configured proxy, work backwards through the
    forwarded chain and choose the nearest untrusted hop. This resists a client
    prepending arbitrary values to a header which the trusted proxy appends to.
    """
    if client_host is None:
        return None
    try:
        peer = ip_address(client_host)
        trusted_networks = [ip_network(proxy, strict=False) for proxy in trusted_proxy_ips]
    except ValueError:
        return client_host
    if not any(peer in network for network in trusted_networks) or not forwarded_for:
        return str(peer)
    try:
        forwarded_hops = [ip_address(hop.strip()) for hop in forwarded_for.split(",")]
    except ValueError:
        return str(peer)
    for hop in reversed(forwarded_hops):
        if not any(hop in network for network in trusted_networks):
            return str(hop)
    return str(peer)


def is_login_allowed(key: str, now: datetime | None = None) -> bool:
    """Return false once the key has reached the failure limit inside the window."""
    current = now or datetime.now(UTC)
    attempts = _login_failures.get(key)
    if attempts is None:
        return True
    cutoff = current - LOGIN_FAILURE_WINDOW
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()
    if not attempts:
        _login_failures.pop(key, None)
        return True
    return len(attempts) < LOGIN_FAILURE_LIMIT


def record_login_failure(key: str, now: datetime | None = None) -> None:
    """Record one failed credential verification for throttling."""
    _login_failures.setdefault(key, deque()).append(now or datetime.now(UTC))


def clear_login_attempts(key: str | None = None) -> None:
    """Clear one successful-login key or all entries for deterministic test cleanup."""
    if key is None:
        _login_failures.clear()
    else:
        _login_failures.pop(key, None)


async def login_user(
    email: str,
    password: str,
    users: UserLookup,
    settings: Settings,
) -> LoginResponse:
    """Authenticate credentials and return an expiring token or one generic failure."""
    user = await authenticate_user(users, email, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email or password")
    token = issue_access_token(
        user,
        signing_key=settings.jwt_signing_key,
        expires_in=timedelta(minutes=settings.jwt_expires_minutes),
    )
    return LoginResponse(access_token=token, role=user.role, user_id=user.user_id)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Return the user represented by a valid, currently signed access token."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        return decode_access_token(
            credentials.credentials, signing_key=settings.jwt_signing_key
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid token") from error


def require_patient(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AuthenticatedUser:
    """Allow only the patient role to access patient session endpoints."""
    if user.role != "patient":
        raise HTTPException(status_code=403, detail="Patients only")
    return user


def require_clinician(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AuthenticatedUser:
    """Allow only the clinician role to access clinician endpoints."""
    if user.role != "clinician":
        raise HTTPException(status_code=403, detail="Clinicians only")
    return user
