"""Unit tests for recording sales, deducting stock and reading dues.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

Tests cover:
- A cash sale with two items is created and returns 201.
- Stock is deducted for every item.
- One ``stock_movements`` row is written per item with the right
  ``balance_after``, ``reference_type`` and ``reference_id``.
- A sale that would drive stock negative returns 409 and saves nothing.
- A mixed sale (one good line, one short line) returns 409 and saves
  nothing: the atomicity proof.
- The server computes the total; a disagreeing client total is rejected.
- A cash sale must be paid in full.
- A credit sale needs a customer, may be part-paid, and creates a due.
- Invalid quantities, empty item lists, inactive customers and missing
  products are rejected.
- The sale writes an audit row.
- Staff may record a sale; an unauthenticated request gets 401.
"""

from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.customer_dues import router as customer_dues_router
from app.api.v1.payments import router as payments_router
from app.api.v1.sales import router as sales_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.stock_movement import StockMovement
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with the auth, sales, payments and dues routers."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(sales_router)
    app.include_router(payments_router)
    app.include_router(customer_dues_router)

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

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(request, exc):
        first_error = exc.errors()[0] if exc.errors() else {}
        msg = first_error.get("msg", "Validation error")
        loc = " -> ".join(str(part) for part in first_error.get("loc", []))
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": f"{loc}: {msg}"}},
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


def _login(client: TestClient, db: Session, username: str, role_name: str | None) -> str:
    """Register a user with a role and return their access token."""
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


def _make_product(db: Session, name: str, stock: str, sale_price: str = "60.00") -> Product:
    """Create a product with the given opening stock and sale price."""
    product = Product(
        category_id=None,
        name=name,
        unit="kg",
        purchase_price=Decimal("50.00"),
        sale_price=Decimal(sale_price),
        current_stock=Decimal(stock),
        low_stock_threshold=Decimal("5.000"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _make_customer(db: Session, name: str, active: bool = True) -> Customer:
    """Create a customer, active unless told otherwise."""
    customer = Customer(name=name, phone=None, is_active=active)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _stock_of(db: Session, product_id: int) -> Decimal:
    """Return the current stock of a product straight from the database."""
    db.expire_all()
    return db.query(Product).filter(Product.id == product_id).one().current_stock


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T1 - a cash sale with two items is created
# ---------------------------------------------------------------------------


def test_cash_sale_with_two_items_returns_201(
    client: TestClient, test_db_session: Session
):
    """T1: a cash sale with two items creates one sale with two items."""
    token = _login(client, test_db_session, "staff_sale_two", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    oil = _make_product(test_db_session, "Oil", "50.000", sale_price="180.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": None,
            "payment_type": "cash",
            "items": [
                {"product_id": rice.id, "quantity": "2.000"},
                {"product_id": oil.id, "quantity": "1.000"},
            ],
            "paid_amount": "300.00",  # 2 * 60 + 1 * 180
            "note": "Walk-in buyer",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["id"] > 0
    assert data["payment_type"] == "cash"
    assert data["total_amount"] == "300.00"
    assert data["paid_amount"] == "300.00"
    assert data["due_amount"] == "0.00"
    assert len(data["items"]) == 2

    assert test_db_session.query(Sale).count() == 1
    assert test_db_session.query(SaleItem).count() == 2


# ---------------------------------------------------------------------------
# T2 - stock is deducted for every item
# ---------------------------------------------------------------------------


def test_stock_is_deducted_for_every_item(
    client: TestClient, test_db_session: Session
):
    """T2: each product loses exactly the quantity that was sold."""
    token = _login(client, test_db_session, "staff_deduct", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    oil = _make_product(test_db_session, "Oil", "50.000", sale_price="180.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [
                {"product_id": rice.id, "quantity": "2.500"},
                {"product_id": oil.id, "quantity": "3.000"},
            ],
            "paid_amount": "690.00",
        },
    )
    assert response.status_code == 201, response.text

    assert _stock_of(test_db_session, rice.id) == Decimal("97.500")
    assert _stock_of(test_db_session, oil.id) == Decimal("47.000")


# ---------------------------------------------------------------------------
# T3 - one stock_movement row per item
# ---------------------------------------------------------------------------


def test_stock_movement_row_is_created_per_item(
    client: TestClient, test_db_session: Session
):
    """T3: each line writes a ``sale`` movement with the right balance."""
    token = _login(client, test_db_session, "staff_movement", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    oil = _make_product(test_db_session, "Oil", "50.000", sale_price="180.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [
                {"product_id": rice.id, "quantity": "10.000"},
                {"product_id": oil.id, "quantity": "5.000"},
            ],
            "paid_amount": "1500.00",
        },
    )
    assert response.status_code == 201, response.text
    sale_id = response.json()["id"]

    movements = (
        test_db_session.query(StockMovement)
        .filter(StockMovement.reference_type == "sale")
        .all()
    )
    assert len(movements) == 2

    by_product = {m.product_id: m for m in movements}
    rice_movement = by_product[rice.id]
    assert rice_movement.movement_type == "sale"
    assert rice_movement.quantity == Decimal("10.000")
    assert rice_movement.balance_after == Decimal("90.000")
    assert rice_movement.reference_type == "sale"
    assert rice_movement.reference_id == sale_id
    assert rice_movement.user_id is not None
    assert rice_movement.note == f"Sale #{sale_id}"

    oil_movement = by_product[oil.id]
    assert oil_movement.quantity == Decimal("5.000")
    assert oil_movement.balance_after == Decimal("45.000")
    assert oil_movement.reference_id == sale_id


# ---------------------------------------------------------------------------
# T4 - a sale that would go negative is rejected and saves nothing
# ---------------------------------------------------------------------------


def test_insufficient_stock_returns_409_and_saves_nothing(
    client: TestClient, test_db_session: Session
):
    """T4: overselling is a 409 and leaves no trace in the database."""
    token = _login(client, test_db_session, "staff_oversell", "staff")
    rice = _make_product(test_db_session, "Rice", "10.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "25.000"}],
            "paid_amount": "1500.00",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert "Rice" in response.json()["error"]["message"]

    assert test_db_session.query(Sale).count() == 0
    assert test_db_session.query(SaleItem).count() == 0
    assert test_db_session.query(StockMovement).count() == 0
    assert _stock_of(test_db_session, rice.id) == Decimal("10.000")


# ---------------------------------------------------------------------------
# T5 - atomicity: one good line and one short line save nothing
# ---------------------------------------------------------------------------


def test_mixed_sale_is_rejected_and_rolls_everything_back(
    client: TestClient, test_db_session: Session
):
    """T5: a sale with one short line saves none of its lines."""
    token = _login(client, test_db_session, "staff_atomic", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    oil = _make_product(test_db_session, "Oil", "2.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [
                {"product_id": rice.id, "quantity": "5.000"},
                {"product_id": oil.id, "quantity": "10.000"},
            ],
            "paid_amount": "900.00",
        },
    )
    assert response.status_code == 409, response.text

    # Nothing at all may survive: no sale, no item, no movement, no stock
    # change on the product that had enough stock.
    assert test_db_session.query(Sale).count() == 0
    assert test_db_session.query(SaleItem).count() == 0
    assert test_db_session.query(StockMovement).count() == 0
    assert test_db_session.query(AuditLog).count() == 0
    assert _stock_of(test_db_session, rice.id) == Decimal("100.000")
    assert _stock_of(test_db_session, oil.id) == Decimal("2.000")


# ---------------------------------------------------------------------------
# T6 - the client total is only a cross-check
# ---------------------------------------------------------------------------


def test_client_total_that_disagrees_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T6: a client total that disagrees with the server total is a 422."""
    token = _login(client, test_db_session, "staff_total", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "120.00",
            "total_amount": "999.00",  # the real total is 120.00
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "TOTAL_MISMATCH"
    assert test_db_session.query(Sale).count() == 0
    assert _stock_of(test_db_session, rice.id) == Decimal("100.000")


# ---------------------------------------------------------------------------
# T7 - a cash sale is paid in full
# ---------------------------------------------------------------------------


def test_cash_sale_with_wrong_paid_amount_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T7: a cash sale whose paid_amount differs from the total is a 422."""
    token = _login(client, test_db_session, "staff_paid", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "100.00",  # the total is 120.00
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_PAID_AMOUNT"
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T8 - a credit sale needs a customer
# ---------------------------------------------------------------------------


def test_credit_sale_without_customer_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T8: a credit sale with no customer is a 422."""
    token = _login(client, test_db_session, "staff_nocustomer", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "0.00",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "CUSTOMER_REQUIRED"
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T9 - a credit sale cannot be over-paid
# ---------------------------------------------------------------------------


def test_credit_sale_paid_more_than_the_total_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T9: paying more than the sale total is a 422."""
    token = _login(client, test_db_session, "staff_overpaid", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Over Payer")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "500.00",  # the total is 120.00
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_PAID_AMOUNT"
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T10 - a quantity must be positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", ["0.000", "-1.000"])
def test_non_positive_quantity_is_rejected(
    client: TestClient, test_db_session: Session, quantity: str
):
    """T10: a zero or negative quantity is a 422."""
    token = _login(client, test_db_session, f"staff_qty_{quantity[:2]}", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": quantity}],
            "paid_amount": "60.00",
        },
    )
    assert response.status_code == 422, response.text
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T11 - a sale needs at least one item
# ---------------------------------------------------------------------------


def test_empty_items_list_is_rejected(client: TestClient, test_db_session: Session):
    """T11: a sale with no items is a 422."""
    token = _login(client, test_db_session, "staff_empty", "staff")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={"payment_type": "cash", "items": [], "paid_amount": "0.00"},
    )
    assert response.status_code == 422, response.text
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T12 - an inactive customer cannot be sold to
# ---------------------------------------------------------------------------


def test_credit_sale_for_inactive_customer_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T12: a credit sale for an inactive customer is a 422."""
    token = _login(client, test_db_session, "staff_inactive_cust", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Inactive Customer", active=False)

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "0.00",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "CUSTOMER_INACTIVE"
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T13 - a missing product is a 404
# ---------------------------------------------------------------------------


def test_sale_for_missing_product_returns_404(
    client: TestClient, test_db_session: Session
):
    """T13: selling a product that does not exist is a 404."""
    token = _login(client, test_db_session, "staff_missing_product", "staff")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": 999999, "quantity": "1.000"}],
            "paid_amount": "60.00",
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T14 - a credit sale creates a due that the dues endpoint can read
# ---------------------------------------------------------------------------


def test_credit_sale_creates_a_readable_due(
    client: TestClient, test_db_session: Session
):
    """T14: the due of a credit sale is readable through the dues endpoint."""
    token = _login(client, test_db_session, "staff_due", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Due Customer")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "4.000"}],
            "paid_amount": "0.00",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["due_amount"] == "240.00"

    due_response = client.get(
        f"/api/v1/customers/{customer.id}/due",
        headers=_auth(token),
    )
    assert due_response.status_code == 200, due_response.text
    data = due_response.json()
    assert data["customer_id"] == customer.id
    assert data["total_credit_sales"] == "240.00"
    assert data["total_paid"] == "0.00"
    assert data["current_due"] == "240.00"
    assert data["sale_count"] == 1
    assert data["payment_count"] == 0


# ---------------------------------------------------------------------------
# T15 - a part payment leaves only the remainder as due
# ---------------------------------------------------------------------------


def test_part_payment_leaves_the_remainder_as_due(
    client: TestClient, test_db_session: Session
):
    """T15: paying part of a credit sale leaves the rest as the due."""
    token = _login(client, test_db_session, "staff_partpay", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Part Payer")

    sale_response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "10.000"}],
            "paid_amount": "100.00",  # part paid at the counter
        },
    )
    assert sale_response.status_code == 201, sale_response.text
    assert sale_response.json()["total_amount"] == "600.00"
    assert sale_response.json()["paid_amount"] == "100.00"
    assert sale_response.json()["due_amount"] == "500.00"

    payment_response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "200.00", "payment_method": "cash"},
    )
    assert payment_response.status_code == 201, payment_response.text

    due_response = client.get(
        f"/api/v1/customers/{customer.id}/due",
        headers=_auth(token),
    )
    data = due_response.json()
    assert data["current_due"] == "300.00"
    assert data["total_credit_sales"] == "600.00"
    assert data["total_paid"] == "300.00"
    assert data["payment_count"] == 1


# ---------------------------------------------------------------------------
# T16 - the audit log
# ---------------------------------------------------------------------------


def test_sale_writes_an_audit_entry(client: TestClient, test_db_session: Session):
    """T16: recording a sale writes a ``sale`` audit row."""
    token = _login(client, test_db_session, "staff_audit_sale", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "120.00",
        },
    )
    assert response.status_code == 201, response.text
    sale_id = response.json()["id"]

    audit = (
        test_db_session.query(AuditLog)
        .filter(AuditLog.entity_type == "sale", AuditLog.entity_id == sale_id)
        .one()
    )
    assert audit.action == "create"
    assert audit.old_value is None
    assert audit.new_value["payment_type"] == "cash"
    assert audit.new_value["total_amount"] == "120.00"
    assert audit.new_value["paid_amount"] == "120.00"
    assert audit.new_value["due_amount"] == "0.00"
    assert len(audit.new_value["items"]) == 1
    assert audit.new_value["items"][0]["product_id"] == rice.id
    assert audit.new_value["items"][0]["quantity"] == "2.000"
    assert audit.new_value["items"][0]["unit_price"] == "60.00"
    assert audit.new_value["items"][0]["line_total"] == "120.00"


# ---------------------------------------------------------------------------
# T17 - roles
# ---------------------------------------------------------------------------


def test_staff_may_create_a_sale(client: TestClient, test_db_session: Session):
    """T17: staff work the counter, so staff may record a sale."""
    token = _login(client, test_db_session, "staff_allowed", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "60.00",
        },
    )
    assert response.status_code == 201, response.text


def test_unauthenticated_sale_request_returns_401(
    client: TestClient, test_db_session: Session
):
    """T17: an unauthenticated sale request is a 401."""
    rice = _make_product(test_db_session, "Rice", "100.000")

    response = client.post(
        "/api/v1/sales",
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "60.00",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_viewer_cannot_read_or_record_sales(
    client: TestClient, test_db_session: Session
):
    """A viewer is forbidden: only owner and staff work the counter."""
    token = _login(client, test_db_session, "viewer_sale", "viewer")
    rice = _make_product(test_db_session, "Rice", "100.000")

    recorded = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "60.00",
        },
    )
    assert recorded.status_code == 403
    assert recorded.json()["error"]["code"] == "FORBIDDEN"

    listed = client.get("/api/v1/sales", headers=_auth(token))
    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "FORBIDDEN"


def test_paid_amount_is_required(client: TestClient, test_db_session: Session):
    """The body contract makes ``paid_amount`` mandatory.

    A cash sale must be paid in full (R5), so the client has to say how much
    it paid. Omitting the field is a 422.
    """
    token = _login(client, test_db_session, "staff_no_paid", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
        },
    )
    assert response.status_code == 422, response.text
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# Extra: reading sales back
# ---------------------------------------------------------------------------


def test_sales_can_be_listed_and_fetched(client: TestClient, test_db_session: Session):
    """A recorded sale is readable through the list and the detail endpoint."""
    token = _login(client, test_db_session, "staff_read", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Reader Customer")

    created = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "0.00",
        },
    )
    assert created.status_code == 201, created.text
    sale_id = created.json()["id"]

    listing = client.get("/api/v1/sales", headers=_auth(token))
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == sale_id

    detail = client.get(f"/api/v1/sales/{sale_id}", headers=_auth(token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["customer_name"] == "Reader Customer"
    assert len(detail.json()["items"]) == 1
    assert detail.json()["payments"] == []

    missing = client.get("/api/v1/sales/999999", headers=_auth(token))
    assert missing.status_code == 404


def test_sales_list_filters_by_payment_type(client: TestClient, test_db_session: Session):
    """The listing can be filtered by payment type."""
    token = _login(client, test_db_session, "staff_filter", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Filter Customer")

    client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "60.00",
        },
    )
    client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "1.000"}],
            "paid_amount": "0.00",
        },
    )

    cash_only = client.get("/api/v1/sales?payment_type=cash", headers=_auth(token))
    assert cash_only.status_code == 200, cash_only.text
    assert cash_only.json()["total"] == 1
    assert cash_only.json()["items"][0]["payment_type"] == "cash"


def test_duplicate_product_lines_are_summed_for_the_stock_check(
    client: TestClient, test_db_session: Session
):
    """R10: the same product twice is summed before the stock check."""
    token = _login(client, test_db_session, "staff_dup", "staff")
    rice = _make_product(test_db_session, "Rice", "10.000")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [
                {"product_id": rice.id, "quantity": "6.000"},
                {"product_id": rice.id, "quantity": "6.000"},
            ],
            "paid_amount": "720.00",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert test_db_session.query(Sale).count() == 0
    assert _stock_of(test_db_session, rice.id) == Decimal("10.000")


# ---------------------------------------------------------------------------
# Integration contract with Azaz's report service (237)
# ---------------------------------------------------------------------------


def test_report_service_reads_the_sales_tables(
    client: TestClient, test_db_session: Session
):
    """Azaz's report service must read the ``sales``/``sale_items`` tables.

    ``app/services/report_service.py`` looks for ``"sales"`` and
    ``"sale_items"`` in the metadata and, once they exist, reads the real
    sales instead of the legacy ``stock_movements`` fallback. This test pins
    the column-name contract so a rename cannot silently zero his reports.
    """
    from app.services import report_service

    token = _login(client, test_db_session, "staff_report", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="100.00")

    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": rice.id, "quantity": "5.000"}],
            "paid_amount": "500.00",
        },
    )
    assert response.status_code == 201, response.text

    # The report service filters on sales.created_at, so the sale has to carry
    # the timestamp it was created with.
    report = report_service.get_daily_sales_report(test_db_session, date.today())
    assert report.sales_count == 1
    assert report.total_sales_amount == Decimal("500.00")
    # Revenue 500.00, cost of goods sold 5 x 50.00 = 250.00.
    assert report.total_profit == Decimal("250.00")


# ---------------------------------------------------------------------------
# R14 - the product row lock
# ---------------------------------------------------------------------------


def test_two_concurrent_sales_cannot_both_pass_the_stock_check(
    test_db_session: Session,
):
    """R14 must hold when two sales of the same product race each other.

    The product row is locked with ``SELECT ... FOR UPDATE`` while the stock
    is checked, so the second transaction waits for the first one to commit and
    then reads the already-deducted stock. Without that lock both sales would
    read the same opening stock, both would pass the check, and the balance
    would end up negative.
    """
    import threading

    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.schemas.sale import SaleCreate, SaleItemIn
    from app.services import sale_service

    # The stock is exactly one unit, so only one of the two sales can win.
    rice = _make_product(test_db_session, "Rice", "1.000", sale_price="60.00")

    user = User(
        full_name="Concurrent Seller",
        username="concurrent_seller",
        email="concurrent_seller@example.com",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        db = sessionmaker(
            bind=test_db_session.get_bind(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )()
        try:
            sale_service.record_sale(
                db,
                SaleCreate(
                    payment_type="cash",
                    items=[SaleItemIn(product_id=rice.id, quantity=Decimal("1.000"))],
                    paid_amount=Decimal("60.00"),
                ),
                user_id=user.id,
            )
            result = "SUCCESS"
        except HTTPException as exc:
            result = exc.detail["code"] if isinstance(exc.detail, dict) else str(exc.detail)
        finally:
            db.close()
        with lock:
            outcomes.append(result)

    def run() -> None:
        # Both threads reach the stock check before either writes, so the row
        # lock is what decides the outcome.
        barrier.wait(timeout=10)
        attempt()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    # Exactly one sale is accepted; the other is refused with a stock conflict.
    assert sorted(outcomes) == ["INSUFFICIENT_STOCK", "SUCCESS"]
    assert test_db_session.query(Sale).count() == 1
    assert test_db_session.query(SaleItem).count() == 1
    # The stock never goes negative.
    assert _stock_of(test_db_session, rice.id) == Decimal("0.000")


# ---------------------------------------------------------------------------
# The sale detail carries its own payments
# ---------------------------------------------------------------------------


def test_sale_detail_lists_the_payments_tied_to_it(
    client: TestClient, test_db_session: Session
):
    """``GET /api/v1/sales/{id}`` returns the sale with its payments.

    A payment may be tied to one credit sale. The sale detail must show those
    payments so the counter can see what has already been paid against a sale.
    """
    token = _login(client, test_db_session, "staff_detail", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Detail Customer")

    sale_response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": rice.id, "quantity": "2.000"}],
            "paid_amount": "0.00",
        },
    )
    assert sale_response.status_code == 201, sale_response.text
    sale_id = sale_response.json()["id"]
    assert sale_response.json()["due_amount"] == "120.00"

    payment_response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "50.00", "sale_id": sale_id},
    )
    assert payment_response.status_code == 201, payment_response.text

    detail = client.get(f"/api/v1/sales/{sale_id}", headers=_auth(token))
    assert detail.status_code == 200, detail.text
    payments = detail.json()["payments"]
    assert len(payments) == 1
    assert payments[0]["id"] == payment_response.json()["id"]
    assert payments[0]["amount"] == "50.00"
    assert payments[0]["sale_id"] == sale_id
    assert payments[0]["customer_id"] == customer.id
