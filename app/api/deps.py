"""Shared FastAPI dependencies: authentication, authorisation and rate limiting.

Owner: Zahid. Imported by every router in ``app/api/v1/``.

The functions here are the single source of truth for "who is calling" and
"what are they allowed to do". Every failure raises ``HTTPException`` whose
detail is already in the PROJECT_RULES.md error shape, so ``app/main.py``
renders it as ``{"error": {"code": ..., "message": ...}}`` without any router
having to build a ``JSONResponse`` by hand.
"""

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.role import Role
from app.models.user import User

# ``auto_error=False`` leaves the 401 to us, so the error body matches the
# shared error shape instead of FastAPI's default ``{"detail": ...}``.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Return the user behind the bearer token.

    Raises 401 when the token is missing, malformed or expired, and when the
    token names a user that no longer exists. An inactive account is a 403,
    not a 401: the credential was valid but the account is not usable.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing authentication token."},
        )

    try:
        payload = decode_token(token, expected_type="access")
        user_id = int(payload.get("sub", 0))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired access token."},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User does not exist."},
        )

    # A deactivated account keeps its token but must not be able to act.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_DISABLED", "message": "User account is disabled."},
        )

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the current user, rejecting accounts that are deactivated.

    ``get_current_user`` already rejects a disabled account, so this is
    equivalent. It exists as an explicit name for endpoints that require an
    active account.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_DISABLED", "message": "User account is disabled."},
        )
    return current_user


# ---------------------------------------------------------------------------
# Authorisation
# ---------------------------------------------------------------------------


def get_role_name(user: User, db: Session) -> str | None:
    """Return the lowercase role name of ``user``, or None when it has no role.

    A user whose role row has been deleted keeps ``role_id`` but resolves to no
    role. That case returns None exactly like a user with no role at all, so
    every caller treats "no role" the same way.
    """
    if not user.role_id:
        return None
    role = db.query(Role).filter(Role.id == user.role_id).first()
    return role.name.lower() if role else None


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    """Build a dependency that only lets a user with one of ``allowed_roles`` through.

    Role names are compared case-insensitively. A user with no role, or with a
    role that is not in the list, is rejected with 403. The allowed roles are
    echoed in the message so the caller can see what was expected.
    """
    allowed = {name.lower() for name in allowed_roles}

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        role_name = get_role_name(current_user, db)
        if role_name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": (
                        "This action requires one of the following roles: "
                        f"{', '.join(sorted(allowed))}."
                    ),
                },
            )
        return current_user

    return _dependency


def require_owner(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that only lets an owner through."""
    if get_role_name(current_user, db) != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Only an owner can perform this action.",
            },
        )
    return current_user


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60

# username -> deque of failure timestamps. ``deque`` keeps the window bounded:
# stale entries are dropped on every access.
_failed_logins: dict[str, deque[float]] = defaultdict(deque)


def _prune_attempts(username: str, now: float) -> deque[float]:
    """Return the failure timestamps for ``username`` still inside the window."""
    attempts = _failed_logins[username]
    cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


def record_failed_login(username: str) -> int:
    """Record a failed login for ``username`` and return the failure count."""
    now = time.time()
    attempts = _prune_attempts(username, now)
    attempts.append(now)
    return len(attempts)


def clear_failed_logins(username: str) -> None:
    """Forget the failure history for ``username`` after a successful login."""
    _failed_logins.pop(username, None)


def is_rate_limited(username: str) -> bool:
    """Return True when ``username`` has exceeded the allowed failed attempts."""
    now = time.time()
    attempts = _prune_attempts(username, now)
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def login_rate_limit_guard(username: str) -> None:
    """Raise 429 when ``username`` is blocked by the failed-login limiter."""
    if is_rate_limited(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "TOO_MANY_ATTEMPTS",
                "message": (
                    "Too many failed login attempts. Please try again in a few minutes."
                ),
            },
        )
