"""Unit tests for Owner dashboard summary endpoint.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.role import Role
from app.models.supplier import Supplier
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and dashboard routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(dashboard_router)

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


def test_dashboard_owner_only_rbac(client: TestClient, test_db_session: Session):
    staff_token = _login(client, test_db_session, "staff_user", "staff")

    res = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {staff_token}"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_dashboard_summary_all_sections(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")

    # 1. Seed Customer
    cust = Customer(name="Customer A", phone="01711223344", is_active=True)
    test_db_session.add(cust)

    # 2. Seed Products (one low-stock, one normal)
    p_low = Product(
        name="Low Stock Sugar",
        unit="kg",
        purchase_price=Decimal("110.00"),
        sale_price=Decimal("130.00"),
        current_stock=Decimal("3.000"),
        low_stock_threshold=Decimal("10.000"),
        is_active=True,
    )
    p_normal = Product(
        name="Abundant Flour",
        unit="kg",
        purchase_price=Decimal("45.00"),
        sale_price=Decimal("55.00"),
        current_stock=Decimal("100.000"),
        low_stock_threshold=Decimal("10.000"),
        is_active=True,
    )
    test_db_session.add_all([p_low, p_normal])

    # 3. Seed Supplier & Purchase
    sup = Supplier(name="Apex Foods", phone="01811223344", is_active=True)
    test_db_session.add(sup)
    test_db_session.commit()

    pur = Purchase(
        supplier_id=sup.id,
        invoice_no="APEX-101",
        total_amount=Decimal("2500.00"),
        note="Initial stock",
    )
    test_db_session.add(pur)
    test_db_session.commit()

    # Call summary endpoint
    res = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    data = res.json()

    # Section 1: Today's sales
    assert "today_sales_amount" in data
    assert "today_sales_count" in data

    # Section 2: Total customer dues
    assert "total_customer_dues" in data

    # Section 3: Low-stock products
    assert data["low_stock_count"] == 1
    assert len(data["low_stock_products"]) == 1
    assert data["low_stock_products"][0]["name"] == "Low Stock Sugar"

    # Section 4: Recent transactions
    assert len(data["recent_transactions"]) >= 1
    t0 = data["recent_transactions"][0]
    assert t0["transaction_type"] == "purchase"
    assert t0["reference_name"] == "Apex Foods"
    assert t0["amount"] == "2500.00"
