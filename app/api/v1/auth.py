"""Authentication endpoints: register, login, refresh, and logout.

Owner: Azaz (Student ID: 237).
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime, timedelta, timezone
import types
import bcrypt
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenOut,
)
from app.schemas.user import UserOut

# ---------------------------------------------------------------------------
# Security helpers (uses Zahid's security module if available, or standard fallback)
# ---------------------------------------------------------------------------

try:
    from app.core.security import (
        create_access_token,
        create_refresh_token,
        decode_token,
        hash_password,
        verify_password,
    )
except ImportError:
    # Passlib / bcrypt compatibility patch for bcrypt>=4.0
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = types.SimpleNamespace(__version__=bcrypt.__version__)

    def hash_password(plain: str) -> str:
        """Hash a plain text password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")

    def verify_password(plain: str, hashed: str) -> bool:
        """Verify plain text password against bcrypt hash."""
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    def create_access_token(user_id: int) -> str:
        """Generate JWT access token valid for ACCESS_TOKEN_EXPIRE_MINUTES (30 mins)."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": expire,
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    def create_refresh_token(user_id: int) -> str:
        """Generate JWT refresh token valid for REFRESH_TOKEN_EXPIRE_DAYS (7 days)."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": expire,
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    def decode_token(token: str, expected_type: str = "access") -> dict:
        """Decode and validate JWT token signature and type."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != expected_type:
                raise ValueError(f"Invalid token type: expected {expected_type}")
            return payload
        except (JWTError, ValueError) as err:
            raise ValueError("Invalid or expired token") from err


# ---------------------------------------------------------------------------
# Database Models: Role and User (fallback if Zahid's models are not yet added)
# ---------------------------------------------------------------------------

from app.core.database import Base

try:
    from app.models.role import Role
except ImportError:
    from sqlalchemy import Identity, Integer, String
    from sqlalchemy.orm import Mapped, mapped_column

    class Role(Base):  # type: ignore[no-redef]
        __tablename__ = "roles"

        id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
        name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
        description: Mapped[str | None] = mapped_column(String(100), nullable=True)

try:
    from app.models.user import User
except ImportError:
    from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, String, func
    from sqlalchemy.orm import Mapped, mapped_column

    class User(Base):  # type: ignore[no-redef]
        __tablename__ = "users"

        id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
        full_name: Mapped[str] = mapped_column(String(100), nullable=False)
        username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
        email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
        password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
        role_id: Mapped[int | None] = mapped_column(
            Integer, ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True
        )
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=False), server_default=func.now(), nullable=False
        )


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

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    summary="Register a new user account",
)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user. Password is stored as a bcrypt hash."""
    # Check duplicate username
    if db.query(User).filter(User.username == body.username).first():
        return _api_error(
            status.HTTP_409_CONFLICT,
            "USERNAME_EXISTS",
            "A user with this username already exists.",
        )

    # Check duplicate email
    if body.email and db.query(User).filter(User.email == body.email).first():
        return _api_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_EXISTS",
            "A user with this email already exists.",
        )

    # Hash password securely using bcrypt
    hashed_password = hash_password(body.password)

    user = User(
        full_name=body.full_name,
        username=body.username,
        email=body.email,
        password_hash=hashed_password,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=TokenOut,
    summary="Log in with username and password",
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with username and password. Returns access and refresh tokens."""
    user = db.query(User).filter(User.username == body.username).first()

    if not user or not verify_password(body.password, user.password_hash):
        return _api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid username or password.",
        )

    if not user.is_active:
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "ACCOUNT_DISABLED",
            "User account is disabled.",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=TokenOut,
    summary="Refresh access token using refresh token",
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access and refresh token pair."""
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_id = int(payload.get("sub", 0))
    except Exception:
        return _api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Invalid or expired refresh token.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "User not found.",
        )

    if not user.is_active:
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "ACCOUNT_DISABLED",
            "User account is disabled.",
        )

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return TokenOut(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=LogoutResponse,
    summary="Log out user",
)
def logout():
    """Log out user. For stateless JWT tokens, client clears local token storage."""
    return LogoutResponse(message="Logged out successfully.")
