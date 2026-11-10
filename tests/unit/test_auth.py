"""Unit tests for authentication and user profile schemas and endpoints.

Owner: Azaz (Student ID: 237).
Tests cover:
- Schema validation rules (passwords, usernames, email, length constraints, strip whitespace)
- Registration endpoint (creates user, bcrypt hash verified, duplicate username/email rejected, response shape)
- Login endpoint (JWT token generation, 30-min access / 7-day refresh, invalid credentials, inactive account)
- Refresh endpoint (valid exchange, rejected access token as refresh, invalid/expired token, inactive account)
- Logout endpoint (successful response)
- User profile endpoints (GET /me, PATCH /me, change password, get by ID, list users)
"""

from datetime import datetime
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.auth import User, decode_token, router as auth_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenOut,
)
from app.schemas.user import PasswordChange, UserAdminUpdate, UserOut, UserProfileUpdate

# ---------------------------------------------------------------------------
# 1. Schema Validation Unit Tests
# ---------------------------------------------------------------------------


def _register_body(**overrides):
    data = {
        "full_name": "Abdullah Azaz",
        "username": "azaz",
        "email": "mdazaz2001@gmail.com",
        "password": "s3cret-password",
    }
    data.update(overrides)
    return RegisterRequest(**data)


def test_register_valid_strips_whitespace():
    body = _register_body(full_name="  Abdullah Azaz  ", username="  azaz  ")
    assert body.full_name == "Abdullah Azaz"
    assert body.username == "azaz"


def test_register_email_is_optional():
    body = _register_body(email=None)
    assert body.email is None


def test_register_rejects_role_id_from_client():
    with pytest.raises(ValidationError):
        _register_body(role_id=1)


@pytest.mark.parametrize("password", ["short", "x" * 73, "পাসওয়ার্ড" * 3])
def test_register_rejects_bad_password(password):
    # Too short (< 8 chars), or > 72 bytes (bcrypt max length)
    with pytest.raises(ValidationError):
        _register_body(password=password)


def test_register_accepts_72_byte_password():
    assert _register_body(password="x" * 72).password == "x" * 72


@pytest.mark.parametrize("username", ["ab", "has space", "a" * 51, "bad!name"])
def test_register_rejects_bad_username(username):
    with pytest.raises(ValidationError):
        _register_body(username=username)


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "a" * 115 + "@x.com"])
def test_register_rejects_bad_email(email):
    with pytest.raises(ValidationError):
        _register_body(email=email)


def test_register_rejects_full_name_too_long():
    with pytest.raises(ValidationError):
        _register_body(full_name="a" * 101)


def test_login_requires_both_fields():
    with pytest.raises(ValidationError):
        LoginRequest(username="azaz")
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="x")


def test_token_out_structure():
    tok = TokenOut(access_token="acc", refresh_token="ref")
    assert tok.model_dump() == {
        "access_token": "acc",
        "refresh_token": "ref",
        "token_type": "bearer",
    }


def test_user_out_never_exposes_password_hash():
    orm_like = SimpleNamespace(
        id=1,
        full_name="Abdullah Azaz",
        username="azaz",
        email=None,
        password_hash="$2b$12$secret",
        role_id=None,
        is_active=True,
        created_at=datetime(2026, 11, 10, 0, 0),
    )
    data = UserOut.model_validate(orm_like).model_dump()
    assert "password_hash" not in data
    assert data["username"] == "azaz"


@pytest.mark.parametrize("field", ["role_id", "is_active", "username", "password_hash"])
def test_profile_update_rejects_protected_fields(field):
    with pytest.raises(ValidationError):
        UserProfileUpdate(**{field: 1})


def test_profile_update_partial():
    body = UserProfileUpdate(email="new@example.com")
    assert body.model_dump(exclude_unset=True) == {"email": "new@example.com"}


def test_profile_update_allows_clearing_email_but_not_full_name():
    assert UserProfileUpdate(email=None).model_dump(exclude_unset=True) == {"email": None}
    with pytest.raises(ValidationError):
        UserProfileUpdate(full_name=None)


def test_password_change_must_differ():
    with pytest.raises(ValidationError):
        PasswordChange(current_password="same-pass1", new_password="same-pass1")


def test_password_change_enforces_new_password_rules():
    with pytest.raises(ValidationError):
        PasswordChange(current_password="old-pass1", new_password="short")


def test_admin_update_rules():
    assert UserAdminUpdate(role_id=None).model_dump(exclude_unset=True) == {"role_id": None}
    with pytest.raises(ValidationError):
        UserAdminUpdate(is_active=None)
    with pytest.raises(ValidationError):
        UserAdminUpdate(role_id=0)


# ---------------------------------------------------------------------------
# 2. Endpoint Integration Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with overridden get_db dependency and error formatting."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)

    @app.exception_handler(HTTPException)
    def http_exception_handler(request, exc):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _login_and_get_token(client: TestClient, username: str = "azaz", password: str = "Password123") -> str:
    """Helper to register and login a user, returning their access token."""
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Azaz Student",
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# 3. Authentication Endpoint Tests
# ---------------------------------------------------------------------------


def test_endpoint_register_success(client: TestClient, test_db_session: Session):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Abdullah Azaz",
            "username": "azaz237",
            "email": "azaz237@example.com",
            "password": "StrongPassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["username"] == "azaz237"
    assert data["email"] == "azaz237@example.com"
    assert data["full_name"] == "Abdullah Azaz"
    assert data["is_active"] is True
    assert "password" not in data
    assert "password_hash" not in data

    # Verify password was hashed in the database using bcrypt
    user_in_db = test_db_session.query(User).filter(User.username == "azaz237").first()
    assert user_in_db is not None
    assert user_in_db.password_hash != "StrongPassword123"
    assert user_in_db.password_hash.startswith("$2b$")


def test_endpoint_register_duplicate_username(client: TestClient):
    payload = {
        "full_name": "User One",
        "username": "unique_user",
        "email": "user1@example.com",
        "password": "Password123",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    payload2 = {
        "full_name": "User Two",
        "username": "unique_user",
        "email": "user2@example.com",
        "password": "Password456",
    }
    res2 = client.post("/api/v1/auth/register", json=payload2)
    assert res2.status_code == 409
    assert res2.json() == {
        "error": {
            "code": "USERNAME_EXISTS",
            "message": "A user with this username already exists.",
        }
    }


def test_endpoint_register_duplicate_email(client: TestClient):
    payload1 = {
        "full_name": "User One",
        "username": "user_alpha",
        "email": "shared@example.com",
        "password": "Password123",
    }
    res1 = client.post("/api/v1/auth/register", json=payload1)
    assert res1.status_code == 201

    payload2 = {
        "full_name": "User Two",
        "username": "user_beta",
        "email": "shared@example.com",
        "password": "Password456",
    }
    res2 = client.post("/api/v1/auth/register", json=payload2)
    assert res2.status_code == 409
    assert res2.json() == {
        "error": {
            "code": "EMAIL_EXISTS",
            "message": "A user with this email already exists.",
        }
    }


def test_endpoint_login_success(client: TestClient):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Login Tester",
            "username": "logintester",
            "password": "ValidPassword99",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "logintester",
            "password": "ValidPassword99",
        },
    )
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    access_payload = jwt.decode(
        tokens["access_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"]
    )
    assert access_payload["type"] == "access"
    assert access_payload["exp"] - access_payload["iat"] == 30 * 60

    refresh_payload = jwt.decode(
        tokens["refresh_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"]
    )
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["exp"] - refresh_payload["iat"] == 7 * 24 * 60 * 60


def test_endpoint_login_invalid_password(client: TestClient):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Login Tester",
            "username": "testuser",
            "password": "CorrectPassword",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid username or password.",
        }
    }


def test_endpoint_login_nonexistent_user(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "ghost_user", "password": "AnyPassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_endpoint_login_disabled_account(client: TestClient, test_db_session: Session):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Disabled User",
            "username": "disabled_user",
            "password": "Password123",
        },
    )
    user = test_db_session.query(User).filter(User.username == "disabled_user").first()
    user.is_active = False
    test_db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "disabled_user", "password": "Password123"},
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "ACCOUNT_DISABLED",
            "message": "User account is disabled.",
        }
    }


def test_endpoint_refresh_success(client: TestClient):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Refresh Tester",
            "username": "refreshtester",
            "password": "Password123",
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "refreshtester", "password": "Password123"},
    )
    refresh_token = login_res.json()["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_endpoint_refresh_rejects_invalid_token(client: TestClient):
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.jwt.token"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "Invalid or expired refresh token.",
        }
    }


def test_endpoint_refresh_rejects_access_token(client: TestClient):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Access Tester",
            "username": "accesstester",
            "password": "Password123",
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "accesstester", "password": "Password123"},
    )
    access_token = login_res.json()["access_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_endpoint_refresh_disabled_account(client: TestClient, test_db_session: Session):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Deactivated User",
            "username": "deactivated_user",
            "password": "Password123",
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "deactivated_user", "password": "Password123"},
    )
    refresh_token = login_res.json()["refresh_token"]

    user = test_db_session.query(User).filter(User.username == "deactivated_user").first()
    user.is_active = False
    test_db_session.commit()

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "ACCOUNT_DISABLED",
            "message": "User account is disabled.",
        }
    }


def test_endpoint_logout(client: TestClient):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully."}


# ---------------------------------------------------------------------------
# 4. User Profile Endpoint Tests
# ---------------------------------------------------------------------------


def test_endpoint_get_my_profile_success(client: TestClient):
    token = _login_and_get_token(client, username="profileuser")
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "profileuser"
    assert data["full_name"] == "Azaz Student"
    assert data["email"] == "profileuser@example.com"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_endpoint_get_my_profile_unauthorized(client: TestClient):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_endpoint_get_my_profile_invalid_token(client: TestClient):
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer bad-token-data"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_endpoint_update_profile_success(client: TestClient):
    token = _login_and_get_token(client, username="updater")
    response = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "full_name": "Updated Full Name",
            "email": "updated@example.com",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Full Name"
    assert data["email"] == "updated@example.com"

    # Verify changes via GET /me
    get_res = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["full_name"] == "Updated Full Name"
    assert get_res.json()["email"] == "updated@example.com"


def test_endpoint_update_profile_duplicate_email(client: TestClient):
    token_a = _login_and_get_token(client, username="usera")
    token_b = _login_and_get_token(client, username="userb")

    response = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"email": "usera@example.com"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "EMAIL_EXISTS",
            "message": "A user with this email already exists.",
        }
    }


def test_endpoint_update_profile_rejects_protected_fields(client: TestClient):
    token = _login_and_get_token(client, username="protect_test")
    # Pydantic extra='forbid' raises 422
    response = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": 99},
    )
    assert response.status_code == 422


def test_endpoint_change_password_success(client: TestClient):
    token = _login_and_get_token(client, username="pwuser", password="OldPassword123")

    response = client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "OldPassword123",
            "new_password": "NewPassword456",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Password changed successfully."}

    # Old password fails login
    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": "pwuser", "password": "OldPassword123"},
    )
    assert old_login.status_code == 401

    # New password succeeds login
    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": "pwuser", "password": "NewPassword456"},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_endpoint_change_password_wrong_current(client: TestClient):
    token = _login_and_get_token(client, username="pwuser2", password="OldPassword123")

    response = client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "WrongPassword99",
            "new_password": "NewPassword456",
        },
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_PASSWORD",
            "message": "Current password is incorrect.",
        }
    }


def test_endpoint_get_user_by_id_success(client: TestClient):
    token = _login_and_get_token(client, username="findme")
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).json()
    user_id = me["id"]

    response = client.get(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "findme"


def test_endpoint_get_user_by_id_not_found(client: TestClient):
    token = _login_and_get_token(client, username="idnotfound")
    response = client.get(
        "/api/v1/users/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "User not found.",
        }
    }


def test_endpoint_list_users(client: TestClient):
    token = _login_and_get_token(client, username="lister")
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert any(u["username"] == "lister" for u in data["items"])
