"""Password hashing and JWT helpers.

Owner: Zahid. Every setting is read from ``app.core.config`` — no secret is
hardcoded here (PROJECT_RULES.md, "Secrets and configuration").

Password hashing uses bcrypt through passlib. The JWT payload carries
``sub`` (the user id), ``role``, ``type`` (``"access"`` or ``"refresh"``),
``iat`` and ``exp``.
"""

import types
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# passlib 1.7.4 reads ``bcrypt.__about__.__version__``, which bcrypt 4.x
# removed. Without this shim passlib raises an AttributeError while probing its
# backend, and falls back to a degraded code path.
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = types.SimpleNamespace(__version__=bcrypt.__version__)

from passlib.context import CryptContext  # noqa: E402

# bcrypt truncates at 72 bytes, so the cost factor is the only tunable here.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password``.

    The plaintext is never stored or logged.
    """
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True when ``plain`` matches ``hashed``.

    A malformed or empty hash returns False rather than raising, so a corrupt
    row cannot crash the login path.
    """
    if not plain or not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def _build_token(payload: dict, expires_delta: timedelta) -> str:
    """Encode ``payload`` with issued-at and expiry timestamps added."""
    now = datetime.now(timezone.utc)
    payload = {**payload, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str | None = None) -> str:
    """Create an access token valid for ``ACCESS_TOKEN_EXPIRE_MINUTES``.

    ``role`` is optional so callers that only know the user id can still mint a
    token; when supplied it is embedded in the payload for authorisation.
    """
    payload: dict = {"sub": str(user_id), "type": "access"}
    if role is not None:
        payload["role"] = role
    return _build_token(payload, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: int) -> str:
    """Create a refresh token valid for ``REFRESH_TOKEN_EXPIRE_DAYS``."""
    payload: dict = {"sub": str(user_id), "type": "refresh"}
    return _build_token(payload, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT, returning its payload.

    Raises ``ValueError`` when the signature is invalid, the token has expired,
    or the token type does not match ``expected_type``.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as err:
        raise ValueError("Invalid or expired token") from err

    if payload.get("type") != expected_type:
        raise ValueError(f"Invalid token type: expected {expected_type}")

    return payload
