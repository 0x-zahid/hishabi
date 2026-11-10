"""Request and response schemas for authentication.

Owner: Azaz (237). Field names and lengths follow the ``users`` table in
``docs/schema.md`` section 3.2.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

# bcrypt only uses the first 72 bytes of a password, so anything longer would be
# silently truncated. Reject it instead of letting two different passwords match.
BCRYPT_MAX_BYTES = 72
PASSWORD_MIN_LENGTH = 8


def _check_password_bytes(value: str) -> str:
    """Reject passwords that bcrypt would silently truncate."""
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes long.")
    return value


Password = Annotated[
    str,
    StringConstraints(min_length=PASSWORD_MIN_LENGTH),
    AfterValidator(_check_password_bytes),
]

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_.-]+$",
    ),
]

Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=120,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class RegisterRequest(BaseModel):
    """Body of the register endpoint. ``role_id`` is never accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName
    username: Username
    email: Email | None = None
    password: Password


class LoginRequest(BaseModel):
    """Body of the login endpoint: username and password as JSON."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    password: Annotated[str, StringConstraints(min_length=1)]


class TokenOut(BaseModel):
    """Access and refresh tokens returned after a successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    """Body of the refresh endpoint."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class LogoutResponse(BaseModel):
    """Response returned upon logout."""

    message: str = "Logged out successfully."
