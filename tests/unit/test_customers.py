"""Unit tests for customer management endpoints.

Owner: Azaz (Student ID: 237). Module 2.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.customers import router as customers_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.role import Role
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and customers routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(customers_router)

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


def test_create_customer_success(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    res = client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Rahim Uddin",
            "phone": "01711223344",
            "email": "rahim@example.com",
            "address": "Dhanmondi, Dhaka",
            "note": "Regular buyer",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] > 0
    assert data["name"] == "Rahim Uddin"
    assert data["phone"] == "01711223344"
    assert data["is_active"] is True

    # Audit log entry check
    log = test_db_session.query(AuditLog).filter(
        AuditLog.entity_type == "customer",
        AuditLog.entity_id == data["id"],
        AuditLog.action == "create",
    ).first()
    assert log is not None
    assert log.new_value["name"] == "Rahim Uddin"


def test_create_customer_staff_allowed(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "staff_user", "staff")
    res = client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Karim Mia", "phone": "01811223344"},
    )
    assert res.status_code == 201
    assert res.json()["name"] == "Karim Mia"


def test_create_customer_duplicate_phone_rejected(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "First User", "phone": "01911223344"},
    )
    res = client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Second User", "phone": "01911223344"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PHONE_EXISTS"


def test_create_customer_blank_fields_normalised(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    res = client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "No Phone User", "phone": "   ", "address": ""},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["phone"] is None
    assert data["address"] is None


def test_list_and_search_customers(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    c1 = Customer(name="Abdullah", phone="01511111111", is_active=True)
    c2 = Customer(name="Barik", phone="01622222222", is_active=True)
    c3 = Customer(name="Anisur", phone="01733333333", is_active=False)
    test_db_session.add_all([c1, c2, c3])
    test_db_session.commit()

    # List all
    res = client.get("/api/v1/customers", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 3

    # Search by name
    res = client.get("/api/v1/customers?search=Ani", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["name"] == "Anisur"

    # Search by phone
    res = client.get("/api/v1/customers?search=01622", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["name"] == "Barik"

    # Filter is_active
    res = client.get("/api/v1/customers?is_active=true", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 2


def test_get_customer_profile(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    cust = Customer(name="Target Cust", phone="01300000000", is_active=True)
    test_db_session.add(cust)
    test_db_session.commit()

    res = client.get(f"/api/v1/customers/{cust.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["name"] == "Target Cust"

    # Not found
    res404 = client.get("/api/v1/customers/99999", headers={"Authorization": f"Bearer {token}"})
    assert res404.status_code == 404
    assert res404.json()["error"]["code"] == "NOT_FOUND"


def test_update_customer(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "staff_user", "staff")
    cust = Customer(name="Old Name", phone="01400000000", is_active=True)
    test_db_session.add(cust)
    test_db_session.commit()

    res = client.patch(
        f"/api/v1/customers/{cust.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name", "address": "New Address"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "New Name"
    assert data["address"] == "New Address"

    # Verify audit log
    log = test_db_session.query(AuditLog).filter(
        AuditLog.entity_type == "customer",
        AuditLog.entity_id == cust.id,
        AuditLog.action == "update",
    ).first()
    assert log is not None
    assert log.old_value["name"] == "Old Name"
    assert log.new_value["name"] == "New Name"


def test_deactivate_customer_owner_only(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    staff_token = _login(client, test_db_session, "staff_user", "staff")
    cust = Customer(name="Active Cust", phone="01799999999", is_active=True)
    test_db_session.add(cust)
    test_db_session.commit()

    # Staff forbidden
    res = client.delete(f"/api/v1/customers/{cust.id}", headers={"Authorization": f"Bearer {staff_token}"})
    assert res.status_code == 403

    # Owner success
    res_del = client.delete(f"/api/v1/customers/{cust.id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_del.status_code == 200
    assert "deactivated" in res_del.json()["message"]

    test_db_session.refresh(cust)
    assert cust.is_active is False


def test_customer_history(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    cust = Customer(name="Hist Cust", phone="01888888888", is_active=True)
    test_db_session.add(cust)
    test_db_session.commit()

    # Create an audit log entry
    log = AuditLog(
        user_id=None,
        action="create",
        entity_type="customer",
        entity_id=cust.id,
        old_value=None,
        new_value={"name": "Hist Cust"},
    )
    test_db_session.add(log)
    test_db_session.commit()

    res = client.get(f"/api/v1/customers/{cust.id}/history", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["customer"]["name"] == "Hist Cust"
    assert data["summary"]["total_sales"] == "0.00"
    assert data["summary"]["current_due"] == "0.00"
    assert len(data["recent_activity"]) >= 1
