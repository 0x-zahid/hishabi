"""Unit tests for role-based access control.

Owner: Zahid. Complies with PROJECT_RULES.md and docs/schema.md.

Tests cover:
- A user with no token is rejected with 401.
- A staff user is rejected with 403 on an owner-only endpoint.
- An owner user is accepted with 200 on the same endpoint.
- A viewer is rejected on an owner-only endpoint.
- A user whose role row was deleted is rejected rather than allowed.
- The failed-login rate limiter blocks after 5 failures and returns 429.
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.deps import (
    MAX_LOGIN_ATTEMPTS,
    clear_failed_logins,
    get_current_user,
    is_rate_limited,
    record_failed_login,
    require_owner,
    require_roles,
)
from app.api.v1.auth import router as auth_router
from app.api.v1.products import router as products_router
from app.core.database import get_db
from app.models.role import Role
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with the auth and product routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(products_router)

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


def _make_role(db: Session, name: str) -> Role:
    """Create a role with ``name`` if it does not exist yet."""
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name, description=f"{name} role")
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def _make_user(db: Session, username: str, role_name: str | None = None) -> User:
    """Create a user, optionally with a role assigned."""
    from app.core.security import hash_password

    user = User(
        full_name=f"User {username}",
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if role_name:
        role = _make_role(db, role_name)
        user.role_id = role.id
        db.commit()
        db.refresh(user)

    return user


def _token_for(client: TestClient, db: Session, username: str, role_name: str | None) -> str:
    """Create a user with a role and return their access token."""
    _make_user(db, username, role_name)
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. No token
# ---------------------------------------------------------------------------


def test_no_token_returns_401(client: TestClient):
    """An unauthenticated request is rejected with 401."""
    response = client.get("/api/v1/products")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_no_token_on_owner_only_endpoint_returns_401(client: TestClient):
    """An unauthenticated request to an owner-only action is rejected with 401."""
    response = client.delete("/api/v1/products/1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_token_returns_401(client: TestClient):
    """A malformed bearer token is rejected with 401."""
    response = client.get(
        "/api/v1/products",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


# ---------------------------------------------------------------------------
# 2. Staff is forbidden, owner is allowed
# ---------------------------------------------------------------------------


def test_staff_gets_403_on_owner_only_endpoint(
    client: TestClient, test_db_session: Session
):
    """A staff user cannot delete a product."""
    token = _token_for(client, test_db_session, "staff_user", "staff")

    response = client.delete(
        "/api/v1/products/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_owner_gets_200_on_owner_only_endpoint(
    client: TestClient, test_db_session: Session
):
    """An owner can delete a product."""
    token = _token_for(client, test_db_session, "owner_user", "owner")

    # Create a product to delete, so the owner passes the role check.
    product = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Rice", "unit": "kg", "sale_price": "60.00"},
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    response = client.delete(
        f"/api/v1/products/{product_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Product deleted successfully."}


def test_viewer_gets_403_on_owner_only_endpoint(
    client: TestClient, test_db_session: Session
):
    """A viewer is forbidden on an owner-only endpoint."""
    token = _token_for(client, test_db_session, "viewer_user", "viewer")

    response = client.delete(
        "/api/v1/products/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_staff_can_create_product(
    client: TestClient, test_db_session: Session
):
    """A staff user is allowed to create a product."""
    token = _token_for(client, test_db_session, "staff_creator", "staff")

    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Flour", "unit": "kg", "sale_price": "50.00"},
    )
    assert response.status_code == 201


def test_user_without_a_role_is_forbidden(
    client: TestClient, test_db_session: Session
):
    """A user with no role is denied rather than silently allowed.

    A missing role used to pass the permission check, because the guard was
    written as ``if role_name and role_name not in [...]``.
    """
    token = _token_for(client, test_db_session, "roleless_user", None)

    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Ghost Item", "unit": "kg", "sale_price": "10.00"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_user_with_deleted_role_is_forbidden(
    client: TestClient, test_db_session: Session
):
    """A user whose role row was deleted is denied, not treated as an owner."""
    token = _token_for(client, test_db_session, "orphan_user", "owner")

    # Delete the role out from under the user.
    role = test_db_session.query(Role).filter(Role.name == "owner").first()
    test_db_session.query(User).filter(User.username == "orphan_user").update(
        {"role_id": None}
    )
    test_db_session.delete(role)
    test_db_session.commit()

    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Orphan Item", "unit": "kg", "sale_price": "10.00"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 3. Dependency factories used directly
# ---------------------------------------------------------------------------


def test_require_roles_allows_matching_role(
    client: TestClient, test_db_session: Session
):
    """require_roles lets a user whose role is on the list through."""
    token = _token_for(client, test_db_session, "allowed_user", "staff")

    app = FastAPI()

    @app.get("/check")
    def check(user: User = Depends(require_roles("owner", "staff"))):
        return {"ok": True, "username": user.username}

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        response = test_client.get("/check", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["ok"] is True


def test_require_roles_rejects_non_matching_role(
    client: TestClient, test_db_session: Session
):
    """require_roles rejects a user whose role is not on the list."""
    token = _token_for(client, test_db_session, "denied_user", "viewer")

    app = FastAPI()

    @app.get("/check")
    def check(user: User = Depends(require_roles("owner", "staff"))):
        return {"ok": True}

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        response = test_client.get("/check", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403


def test_require_owner_rejects_staff(
    client: TestClient, test_db_session: Session
):
    """require_owner rejects a staff user."""
    token = _token_for(client, test_db_session, "staff_only", "staff")

    app = FastAPI()

    @app.get("/owner-only")
    def check(user: User = Depends(require_owner)):
        return {"ok": True}

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        response = test_client.get(
            "/owner-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403


def test_require_owner_accepts_owner(
    client: TestClient, test_db_session: Session
):
    """require_owner accepts an owner user."""
    token = _token_for(client, test_db_session, "the_owner", "owner")

    app = FastAPI()

    @app.get("/owner-only")
    def check(user: User = Depends(require_owner)):
        return {"ok": True, "username": user.username}

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        response = test_client.get(
            "/owner-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["username"] == "the_owner"


def test_inactive_user_is_rejected_with_403(
    client: TestClient, test_db_session: Session
):
    """A deactivated account cannot use its token."""
    token = _token_for(client, test_db_session, "disabled_user", "staff")

    user = test_db_session.query(User).filter(User.username == "disabled_user").first()
    user.is_active = False
    test_db_session.commit()

    response = client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


# ---------------------------------------------------------------------------
# 4. Failed-login rate limiting
# ---------------------------------------------------------------------------


def test_rate_limiter_blocks_after_five_failures():
    """The username is blocked once it reaches the allowed failure count."""
    username = "brute_force_target"
    clear_failed_logins(username)

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        record_failed_login(username)
        assert is_rate_limited(username) is False

    record_failed_login(username)
    assert is_rate_limited(username) is True

    clear_failed_logins(username)
    assert is_rate_limited(username) is False


def test_rate_limiter_is_per_username():
    """One blocked username does not block another."""
    clear_failed_logins("blocked_one")
    clear_failed_logins("innocent_two")

    for _ in range(MAX_LOGIN_ATTEMPTS):
        record_failed_login("blocked_one")

    assert is_rate_limited("blocked_one") is True
    assert is_rate_limited("innocent_two") is False

    clear_failed_logins("blocked_one")
    clear_failed_logins("innocent_two")


def test_rate_limit_guard_raises_429():
    """The guard raises a 429 with the shared error shape."""
    from fastapi import status as http_status

    from app.api.deps import login_rate_limit_guard

    username = "guarded_user"
    clear_failed_logins(username)
    for _ in range(MAX_LOGIN_ATTEMPTS):
        record_failed_login(username)

    with pytest.raises(HTTPException) as exc_info:
        login_rate_limit_guard(username)

    assert exc_info.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
    assert exc_info.value.detail["code"] == "TOO_MANY_ATTEMPTS"

    clear_failed_logins(username)
