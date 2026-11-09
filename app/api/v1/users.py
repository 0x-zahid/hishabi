"""User profile and user management endpoints.

Owner: Azaz (Student ID: 237).
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.user import (
    MessageResponse,
    PasswordChange,
    UserListOut,
    UserOut,
    UserProfileUpdate,
)

# ---------------------------------------------------------------------------
# Security helpers (uses Zahid's security module if available, or auth fallback)
# ---------------------------------------------------------------------------

try:
    from app.core.security import decode_token, hash_password, verify_password
except ImportError:
    from app.api.v1.auth import decode_token, hash_password, verify_password


# ---------------------------------------------------------------------------
# Database Model: User (uses Zahid's model if available, or auth fallback)
# ---------------------------------------------------------------------------

try:
    from app.models.user import User
except ImportError:
    from app.api.v1.auth import User

try:
    from app.models.role import Role
except ImportError:
    from app.api.v1.auth import Role


# ---------------------------------------------------------------------------
# Current User Dependency (uses Zahid's deps module if available, or standard fallback)
# ---------------------------------------------------------------------------

_http_bearer = HTTPBearer(auto_error=False)

try:
    from app.api.deps import get_current_user
except ImportError:

    def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
        db: Session = Depends(get_db),
    ) -> User:
        """Authenticate user from bearer token header."""
        if not credentials or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Missing authentication token."},
            )
        try:
            payload = decode_token(credentials.credentials, expected_type="access")
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

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_DISABLED", "message": "User account is disabled."},
            )

        return user


# ---------------------------------------------------------------------------
# Helper to produce standard API error responses per PROJECT_RULES.md
# ---------------------------------------------------------------------------


def _api_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserOut,
    summary="Get current user profile",
)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Retrieve profile of currently authenticated user."""
    return current_user


@router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserOut,
    summary="Update current user profile",
)
@router.put(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserOut,
    include_in_schema=False,
)
def update_my_profile(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update profile fields (full_name, email). Protected fields like role_id are rejected."""
    update_data = body.model_dump(exclude_unset=True)

    # Check email duplicate if email is being updated
    if "email" in update_data and update_data["email"] != current_user.email:
        new_email = update_data["email"]
        if new_email is not None:
            existing = (
                db.query(User)
                .filter(User.email == new_email, User.id != current_user.id)
                .first()
            )
            if existing:
                return _api_error(
                    status.HTTP_409_CONFLICT,
                    "EMAIL_EXISTS",
                    "A user with this email already exists.",
                )
        current_user.email = new_email

    if "full_name" in update_data and update_data["full_name"] is not None:
        current_user.full_name = update_data["full_name"]

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post(
    "/me/change-password",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Change password for current user",
)
@router.put(
    "/me/password",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    include_in_schema=False,
)
def change_password(
    body: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user password after verifying existing password."""
    if not verify_password(body.current_password, current_user.password_hash):
        return _api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_PASSWORD",
            "Current password is incorrect.",
        )

    current_user.password_hash = hash_password(body.new_password)
    db.commit()

    return MessageResponse(message="Password changed successfully.")


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=UserListOut,
    summary="List all users",
)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List users in the standard items and total shape."""
    query = db.query(User)
    total = query.count()
    users = query.offset(skip).limit(limit).all()
    return UserListOut(items=users, total=total)


@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=UserOut,
    summary="Get user by ID",
)
def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details of a user by user_id."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "User not found.",
        )
    return user
