"""v0 stand-in for login. Real users, passwords and JWTs come in M4-02.

The token is a fixed string per role, so the flow (log in, send a Bearer token,
get 401/403) already works end to end, but nothing here is secure yet.
"""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import Settings
from app.schemas import LoginResponse, Role

# Reads env vars (e.g. MIRROR_DEMO_PASSWORD), falling back to config.py defaults.
settings = Settings()


class DemoUser(BaseModel):
    """A v0 stand-in for a row in the users table (ids match services/db/seed.sh)."""

    user_id: str
    email: str
    role: Role
    token: str


DEMO_USERS = [
    DemoUser(user_id="00000000-0000-0000-0000-000000000101", email="clinician.ada@example.test", role="clinician", token="dev-clinician-token"),
    DemoUser(user_id="00000000-0000-0000-0000-000000000201", email="patient.alex@example.test", role="patient", token="dev-patient-token"),
    DemoUser(user_id="00000000-0000-0000-0000-000000000202", email="patient.bri@example.test", role="patient", token="dev-patient-b-token"),
]

USERS_BY_TOKEN = {user.token: user for user in DEMO_USERS}
USERS_BY_EMAIL = {user.email: user for user in DEMO_USERS}

# Declares "Authorization: Bearer <token>" as a security scheme (the contract's
# bearerAuth). auto_error=False lets us return our own 401 message.
bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def demo_login(email: str, password: str) -> LoginResponse:
    user = USERS_BY_EMAIL.get(email.lower())
    if user is None or password != settings.mirror_demo_password:
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return LoginResponse(access_token=user.token, role=user.role, user_id=user.user_id)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> DemoUser:
    """401 if there is no valid token; otherwise the caller."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    user = USERS_BY_TOKEN.get(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def require_patient(user: Annotated[DemoUser, Depends(current_user)]) -> DemoUser:
    """403 if the caller is logged in but is not a patient."""
    if user.role != "patient":
        raise HTTPException(status_code=403, detail="Patients only")
    return user