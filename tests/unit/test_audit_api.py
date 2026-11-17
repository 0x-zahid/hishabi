"""Unit tests for audit log query endpoints.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and audit routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(audit_router)

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
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name, description=f"{name} role")
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def _login(client: TestClient, db: Session, username: str, role_name: str | None) -> str:
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

    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_audit_owner_only_rbac(client: TestClient, test_db_session: Session):
    staff_token = _login(client, test_db_session, "staff_user", "staff")

    res = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {staff_token}"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    res_detail = client.get("/api/v1/audit/1", headers={"Authorization": f"Bearer {staff_token}"})
    assert res_detail.status_code == 403


def test_list_audit_logs_and_filters(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")

    # Insert 3 audit logs
    l1 = AuditLog(
        action="create",
        entity_type="product",
        entity_id=1,
        new_value={"name": "Rice", "sale_price": "100.00"},
        created_at=datetime(2026, 11, 10, 10, 0, 0),
    )
    l2 = AuditLog(
        action="update",
        entity_type="product",
        entity_id=1,
        old_value={"name": "Rice"},
        new_value={"name": "Basmati Rice"},
        created_at=datetime(2026, 11, 12, 11, 0, 0),
    )
    l3 = AuditLog(
        action="create",
        entity_type="customer",
        entity_id=1,
        new_value={"name": "Rahim"},
        created_at=datetime(2026, 11, 15, 12, 0, 0),
    )
    test_db_session.add_all([l1, l2, l3])
    test_db_session.commit()

    # List all (including the login audit logs if any)
    res = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    assert res.json()["total"] >= 3

    # Filter by entity_type=product
    res_prod = client.get("/api/v1/audit?entity_type=product", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_prod.status_code == 200
    assert res_prod.json()["total"] == 2

    # Filter by action=update
    res_upd = client.get("/api/v1/audit?action=update", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_upd.status_code == 200
    assert res_upd.json()["total"] == 1
    assert res_upd.json()["items"][0]["entity_type"] == "product"


def test_audit_detail_and_password_stripping(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")

    # Insert log with sensitive password_hash and token
    log = AuditLog(
        action="user_register",
        entity_type="user",
        entity_id=2,
        new_value={
            "username": "newuser",
            "password_hash": "$2b$12$secretHashValue123",
            "token": "sensitiveJwtTokenValue",
            "email": "user@example.com",
        },
        created_at=datetime(2026, 11, 18, 12, 0, 0),
    )
    test_db_session.add(log)
    test_db_session.commit()
    test_db_session.refresh(log)

    res = client.get(f"/api/v1/audit/{log.id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "user_register"
    assert data["new_value"]["username"] == "newuser"
    assert data["new_value"]["email"] == "user@example.com"
    # Verify sensitive fields are strictly stripped!
    assert "password_hash" not in data["new_value"]
    assert "token" not in data["new_value"]


def test_audit_detail_not_found(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    res = client.get("/api/v1/audit/99999", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"
