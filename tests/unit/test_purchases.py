"""Unit tests for purchase recording and stock increase.

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
from app.api.v1.purchases import router as purchases_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.role import Role
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.models.user import User


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with auth and purchases routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(purchases_router)

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


def _seed_supplier_and_products(db: Session):
    supplier = Supplier(name="Test Supplier Co", phone="01711000000", is_active=True)
    db.add(supplier)

    p1 = Product(
        name="Miniket Rice",
        unit="kg",
        purchase_price=Decimal("60.00"),
        sale_price=Decimal("70.00"),
        current_stock=Decimal("50.000"),
        low_stock_threshold=Decimal("10.000"),
        is_active=True,
    )
    p2 = Product(
        name="Soybean Oil",
        unit="ltr",
        purchase_price=Decimal("150.00"),
        sale_price=Decimal("170.00"),
        current_stock=Decimal("20.000"),
        low_stock_threshold=Decimal("5.000"),
        is_active=True,
    )
    db.add_all([p1, p2])
    db.commit()
    db.refresh(supplier)
    db.refresh(p1)
    db.refresh(p2)
    return supplier, p1, p2


def test_record_purchase_success_and_stock_increase(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "staff_user", "staff")
    supplier, p1, p2 = _seed_supplier_and_products(test_db_session)

    res = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "invoice_no": "INV-2026-001",
            "note": "Weekly restock",
            "items": [
                {"product_id": p1.id, "quantity": "10.000", "unit_cost": "62.00"},
                {"product_id": p2.id, "quantity": "5.000", "unit_cost": "155.00"},
            ],
            # 10 * 62 = 620.00; 5 * 155 = 775.00; total = 1395.00
            "total_amount": "1395.00",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["id"] > 0
    assert data["supplier_name"] == "Test Supplier Co"
    assert data["total_amount"] == "1395.00"
    assert len(data["items"]) == 2

    # Verify stock increased automatically
    test_db_session.refresh(p1)
    test_db_session.refresh(p2)
    assert p1.current_stock == Decimal("60.000")  # 50 + 10
    assert p2.current_stock == Decimal("25.000")  # 20 + 5

    # Verify stock movements created
    movements = test_db_session.query(StockMovement).filter(
        StockMovement.reference_type == "purchase",
        StockMovement.reference_id == data["id"],
    ).all()
    assert len(movements) == 2
    m1 = [m for m in movements if m.product_id == p1.id][0]
    assert m1.movement_type == "purchase"
    assert m1.quantity == Decimal("10.000")
    assert m1.balance_after == Decimal("60.000")

    # Verify audit log
    log = test_db_session.query(AuditLog).filter(
        AuditLog.entity_type == "purchase",
        AuditLog.entity_id == data["id"],
        AuditLog.action == "create",
    ).first()
    assert log is not None
    assert log.new_value["total_amount"] == "1395.00"


def test_record_purchase_total_mismatch_rejected(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    supplier, p1, _ = _seed_supplier_and_products(test_db_session)

    res = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": p1.id, "quantity": "10.000", "unit_cost": "60.00"}],
            "total_amount": "999.00",  # Mismatch (should be 600.00)
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "TOTAL_MISMATCH"

    # Verify rollback: stock remains untouched
    test_db_session.refresh(p1)
    assert p1.current_stock == Decimal("50.000")


def test_record_purchase_duplicate_product_rejected(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    supplier, p1, _ = _seed_supplier_and_products(test_db_session)

    res = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "items": [
                {"product_id": p1.id, "quantity": "5.000", "unit_cost": "60.00"},
                {"product_id": p1.id, "quantity": "5.000", "unit_cost": "60.00"},
            ],
        },
    )
    assert res.status_code == 422


def test_record_purchase_inactive_supplier_rejected(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    supplier, p1, _ = _seed_supplier_and_products(test_db_session)
    supplier.is_active = False
    test_db_session.commit()

    res = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": p1.id, "quantity": "5.000", "unit_cost": "60.00"}],
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SUPPLIER_INACTIVE"


def test_record_purchase_inactive_product_rejected_and_rollback(
    client: TestClient, test_db_session: Session
):
    token = _login(client, test_db_session, "owner_user", "owner")
    supplier, p1, p2 = _seed_supplier_and_products(test_db_session)
    p2.is_active = False
    test_db_session.commit()

    res = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "items": [
                {"product_id": p1.id, "quantity": "10.000", "unit_cost": "60.00"},
                {"product_id": p2.id, "quantity": "5.000", "unit_cost": "150.00"},
            ],
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PRODUCT_INACTIVE"

    # Entire transaction must rollback: p1 stock must NOT increase
    test_db_session.refresh(p1)
    assert p1.current_stock == Decimal("50.000")
    assert test_db_session.query(Purchase).count() == 0
    assert test_db_session.query(StockMovement).count() == 0


def test_list_and_get_purchases(client: TestClient, test_db_session: Session):
    token = _login(client, test_db_session, "owner_user", "owner")
    supplier, p1, _ = _seed_supplier_and_products(test_db_session)

    # Record two purchases
    client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "invoice_no": "INV-1",
            "items": [{"product_id": p1.id, "quantity": "5.000", "unit_cost": "60.00"}],
        },
    )
    res2 = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier.id,
            "invoice_no": "INV-2",
            "items": [{"product_id": p1.id, "quantity": "8.000", "unit_cost": "60.00"}],
        },
    )
    p2_id = res2.json()["id"]

    # List
    res_list = client.get("/api/v1/purchases", headers={"Authorization": f"Bearer {token}"})
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 2

    # Filter by supplier
    res_sup = client.get(
        f"/api/v1/purchases?supplier_id={supplier.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_sup.status_code == 200
    assert res_sup.json()["total"] == 2

    # Get single
    res_single = client.get(f"/api/v1/purchases/{p2_id}", headers={"Authorization": f"Bearer {token}"})
    assert res_single.status_code == 200
    data = res_single.json()
    assert data["invoice_no"] == "INV-2"
    assert data["total_amount"] == "480.00"  # 8 * 60
    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "Miniket Rice"


def test_purchase_rbac_permissions(client: TestClient, test_db_session: Session):
    supplier, p1, _ = _seed_supplier_and_products(test_db_session)
    viewer_token = _login(client, test_db_session, "viewer_user", "viewer")

    # Viewer cannot record purchases (403)
    res_post = client.post(
        "/api/v1/purchases",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": p1.id, "quantity": "5.000", "unit_cost": "60.00"}],
        },
    )
    assert res_post.status_code == 403

    # Viewer CAN read purchases (200)
    res_get = client.get("/api/v1/purchases", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_get.status_code == 200

    # Unauthenticated rejected (401)
    res_unauth = client.get("/api/v1/purchases")
    assert res_unauth.status_code == 401
