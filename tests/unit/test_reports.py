"""Unit tests for business reports and file exports.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.reports import router as reports_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.product import Product
from app.models.role import Role
from app.models.stock_movement import StockMovement
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and reports routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(reports_router)

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


def _seed_products_and_sales(db: Session, target_date: date):
    """Seed products and sales stock movements on target_date."""
    p1 = Product(
        name="Basmati Rice",
        unit="kg",
        purchase_price=Decimal("80.00"),  # Cost
        sale_price=Decimal("100.00"),    # Revenue
        current_stock=Decimal("100.000"),
        is_active=True,
    )
    p2 = Product(
        name="Sunflower Oil",
        unit="ltr",
        purchase_price=Decimal("150.00"),  # Cost
        sale_price=Decimal("180.00"),     # Revenue
        current_stock=Decimal("50.000"),
        is_active=True,
    )
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)

    # Add 2 sales movements on target_date
    # Sale 1: 5 kg p1 -> rev = 500, cost = 400, profit = 100
    # Sale 2: 2 ltr p2 -> rev = 360, cost = 300, profit = 60
    # Total revenue = 860, Total cost = 700, Total profit = 160
    dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0)
    m1 = StockMovement(
        product_id=p1.id,
        movement_type="sale",
        quantity=Decimal("5.000"),
        balance_after=Decimal("95.000"),
        created_at=dt,
    )
    m2 = StockMovement(
        product_id=p2.id,
        movement_type="sale",
        quantity=Decimal("2.000"),
        balance_after=Decimal("48.000"),
        created_at=dt,
    )
    db.add_all([m1, m2])
    db.commit()
    return p1, p2


def test_reports_owner_only_rbac(client: TestClient, test_db_session: Session):
    staff_token = _login(client, test_db_session, "staff_user", "staff")

    # Staff gets 403 on all report endpoints
    for path in [
        "/api/v1/reports/daily?date=2026-11-18",
        "/api/v1/reports/monthly?year=2026&month=11",
        "/api/v1/reports/dues",
        "/api/v1/reports/profit?start=2026-11-01&end=2026-11-18",
        "/api/v1/reports/daily/export?format=pdf&date=2026-11-18",
    ]:
        res = client.get(path, headers={"Authorization": f"Bearer {staff_token}"})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"


def test_daily_sales_report(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    today = date(2026, 11, 18)
    _seed_products_and_sales(test_db_session, today)

    res = client.get(
        f"/api/v1/reports/daily?date={today.isoformat()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["date"] == "2026-11-18"
    assert data["sales_count"] == 2
    assert data["total_sales_amount"] == "860.00"
    assert data["total_profit"] == "160.00"
    assert data["cash_sales_amount"] == "860.00"
    assert data["credit_sales_amount"] == "0.00"


def test_monthly_sales_report(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    day = date(2026, 11, 15)
    _seed_products_and_sales(test_db_session, day)

    res = client.get(
        "/api/v1/reports/monthly?year=2026&month=11",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["year"] == 2026
    assert data["month"] == 11
    assert data["total_sales_amount"] == "860.00"
    assert data["total_profit"] == "160.00"
    assert len(data["days"]) == 30  # November has 30 days


def test_dues_report(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    c1 = Customer(name="Hasan Ali", phone="01711001122", is_active=True)
    c2 = Customer(name="Tareq Mahmud", phone="01822003344", is_active=True)
    test_db_session.add_all([c1, c2])
    test_db_session.commit()

    res = client.get("/api/v1/reports/dues", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["customer_count"] == 2
    assert data["total_due_amount"] == "0.00"
    assert len(data["customers"]) == 2


def test_profit_report(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    day = date(2026, 11, 10)
    _seed_products_and_sales(test_db_session, day)

    res = client.get(
        "/api/v1/reports/profit?start=2026-11-01&end=2026-11-30",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_revenue"] == "860.00"
    assert data["total_cogs"] == "700.00"
    assert data["gross_profit"] == "160.00"


def test_pdf_export_streaming(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    today = date(2026, 11, 18)
    _seed_products_and_sales(test_db_session, today)

    # Test PDF export
    res = client.get(
        f"/api/v1/reports/daily/export?format=pdf&date={today.isoformat()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in res.headers["content-disposition"]
    # PDF files start with %PDF
    assert res.content.startswith(b"%PDF")
    assert len(res.content) > 100


def test_excel_export_streaming(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")
    today = date(2026, 11, 18)
    _seed_products_and_sales(test_db_session, today)

    # Test Excel export
    res = client.get(
        f"/api/v1/reports/daily/export?format=xlsx&date={today.isoformat()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    assert "attachment; filename=" in res.headers["content-disposition"]
    # XLSX files are ZIP archives starting with PK\x03\x04
    assert res.content.startswith(b"PK\x03\x04")
    assert len(res.content) > 100


def test_invalid_report_type_or_format(client: TestClient, test_db_session: Session):
    owner_token = _login(client, test_db_session, "owner_user", "owner")

    res1 = client.get(
        "/api/v1/reports/unknown/export?format=pdf",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res1.status_code == 400
    assert res1.json()["error"]["code"] == "INVALID_REPORT_TYPE"

    res2 = client.get(
        "/api/v1/reports/daily/export?format=csv",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "INVALID_FORMAT"
