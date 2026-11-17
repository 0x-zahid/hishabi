"""Unit tests for supplier management endpoints.

Owner: Azaz (Student ID: 237). Module 2.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.suppliers import router as suppliers_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.purchase import Purchase
from app.models.role import Role
from app.models.supplier import Supplier
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and suppliers routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(suppliers_router)

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


def test_create_supplier_success(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    res = client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Square Consumer Products",
            "phone": "01700112233",
            "email": "contact@square.com",
            "contact_person": "Tanvir Hasan",
            "address": "Uttara, Dhaka",
            "note": "Primary FMCG vendor",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] > 0
    assert data["name"] == "Square Consumer Products"
    assert data["contact_person"] == "Tanvir Hasan"

    # Audit log check
    log = test_db_session.query(AuditLog).filter(
        AuditLog.entity_type == "supplier",
        AuditLog.entity_id == data["id"],
        AuditLog.action == "create",
    ).first()
    assert log is not None
    assert log.new_value["name"] == "Square Consumer Products"


def test_create_supplier_duplicate_phone_rejected(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Supplier A", "phone": "01800112233"},
    )
    res = client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Supplier B", "phone": "01800112233"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PHONE_EXISTS"


def test_list_and_search_suppliers(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    s1 = Supplier(name="Meghna Group", phone="01711111111", contact_person="Kamal", is_active=True)
    s2 = Supplier(name="City Group", phone="01822222222", contact_person="Jamal", is_active=True)
    s3 = Supplier(name="Akij Group", phone="01933333333", contact_person="Salam", is_active=False)
    test_db_session.add_all([s1, s2, s3])
    test_db_session.commit()

    # List all
    res = client.get("/api/v1/suppliers", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 3

    # Search by contact person
    res = client.get("/api/v1/suppliers?search=Kamal", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["name"] == "Meghna Group"

    # Filter active
    res = client.get("/api/v1/suppliers?is_active=true", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 2


def test_get_supplier_detail_with_stats(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    sup = Supplier(name="PRAN Agro", phone="01600000000", is_active=True)
    test_db_session.add(sup)
    test_db_session.commit()

    # Add dummy purchase record
    p1 = Purchase(supplier_id=sup.id, total_amount=Decimal("1500.00"), invoice_no="INV-1")
    p2 = Purchase(supplier_id=sup.id, total_amount=Decimal("2500.00"), invoice_no="INV-2")
    test_db_session.add_all([p1, p2])
    test_db_session.commit()

    res = client.get(f"/api/v1/suppliers/{sup.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "PRAN Agro"
    assert data["purchase_count"] == 2
    assert data["total_purchased"] == "4000.00"


def test_update_supplier(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "staff_user", "staff")
    sup = Supplier(name="ACI Limited", phone="01500000000", is_active=True)
    test_db_session.add(sup)
    test_db_session.commit()

    res = client.patch(
        f"/api/v1/suppliers/{sup.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_person": "Dr. Arif", "address": "Tejgaon, Dhaka"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["contact_person"] == "Dr. Arif"
    assert data["address"] == "Tejgaon, Dhaka"

    # Verify audit log
    log = test_db_session.query(AuditLog).filter(
        AuditLog.entity_type == "supplier",
        AuditLog.entity_id == sup.id,
        AuditLog.action == "update",
    ).first()
    assert log is not None
    assert log.new_value["contact_person"] == "Dr. Arif"


def test_deactivate_supplier_owner_only(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    staff_token = _login(client, test_db_session, "staff_user", "staff")
    sup = Supplier(name="Old Supplier", phone="01311112222", is_active=True)
    test_db_session.add(sup)
    test_db_session.commit()

    # Staff forbidden
    res = client.delete(f"/api/v1/suppliers/{sup.id}", headers={"Authorization": f"Bearer {staff_token}"})
    assert res.status_code == 403

    # Owner success
    res_del = client.delete(f"/api/v1/suppliers/{sup.id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_del.status_code == 200
    assert "deactivated" in res_del.json()["message"]

    test_db_session.refresh(sup)
    assert sup.is_active is False
