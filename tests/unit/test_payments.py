"""Unit tests for customer payments and customer dues.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

Tests cover:
- Recording a payment returns 201 and reduces the customer's due.
- A payment of exactly the due is allowed and leaves a due of zero.
- An overpayment is a 422 and the due is unchanged.
- Two concurrent payments cannot both pass the overpayment check (R17).
- A zero or negative amount is a 422.
- A payment for an inactive customer is a 422, for a missing one a 404.
- The payment history is returned newest first.
- The due endpoint lists every customer with a due and omits the others.
- The payment writes an audit row.
- Staff may record a payment; an unauthenticated request gets 401.
"""

import threading
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session, sessionmaker

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
from app.models.user import User
from app.schemas.payment import PaymentCreate
from app.schemas.sale import SaleCreate, SaleItemIn


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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _credit_sale(
    client: TestClient,
    token: str,
    product: Product,
    customer: Customer,
    quantity: str = "10.000",
    paid_amount: str = "0.00",
) -> int:
    """Record a credit sale and return its id."""
    response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "payment_type": "credit",
            "items": [{"product_id": product.id, "quantity": quantity}],
            "paid_amount": paid_amount,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _login_standalone(db: Session, username: str, role_name: str | None) -> str:
    """Create a user with a role and return their id.

    The concurrency test drives the service directly, so it does not need an
    HTTP login; it only needs a real user id for the foreign key.
    """
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
    return user.id


def _user_id(db: Session, username: str) -> int:
    """Return the id of a user created by ``_login_standalone``."""
    user = db.query(User).filter(User.username == username).first()
    assert user is not None
    return user.id


def _credit_sale_standalone(
    db: Session, product: Product, customer: Customer, quantity: str
) -> None:
    """Record a credit sale straight through the service."""
    from app.services import sale_service

    sale_service.record_sale(
        db,
        SaleCreate(
            customer_id=customer.id,
            payment_type="credit",
            items=[SaleItemIn(product_id=product.id, quantity=Decimal(quantity))],
            paid_amount=Decimal("0.00"),
        ),
        user_id=_user_id(db, "staff_concurrent"),
    )


# ---------------------------------------------------------------------------
# T18 - a payment reduces the due
# ---------------------------------------------------------------------------


def test_payment_reduces_the_customer_due(client: TestClient, test_db_session: Session):
    """T18: recording a payment returns 201 and lowers the outstanding due."""
    token = _login(client, test_db_session, "staff_pay", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Paying Customer")

    _credit_sale(client, token, rice, customer, quantity="10.000")  # 600.00 due

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "amount": "250.00",
            "payment_method": "bkash",
            "note": "Part payment",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["id"] > 0
    assert data["amount"] == "250.00"
    assert data["customer_id"] == customer.id
    assert data["payment_method"] == "bkash"

    due = client.get(f"/api/v1/customers/{customer.id}/due", headers=_auth(token))
    assert due.status_code == 200, due.text
    assert due.json()["current_due"] == "350.00"
    assert due.json()["total_paid"] == "250.00"
    assert due.json()["payment_count"] == 1


# ---------------------------------------------------------------------------
# T19 - a payment of exactly the due is allowed
# ---------------------------------------------------------------------------


def test_payment_of_the_exact_due_is_allowed(client: TestClient, test_db_session: Session):
    """T19: paying the exact due leaves a due of zero."""
    token = _login(client, test_db_session, "staff_exact", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Exact Payer")

    _credit_sale(client, token, rice, customer, quantity="4.000")  # 240.00 due

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "240.00"},
    )
    assert response.status_code == 201, response.text

    due = client.get(f"/api/v1/customers/{customer.id}/due", headers=_auth(token))
    assert due.json()["current_due"] == "0.00"


# ---------------------------------------------------------------------------
# T20 - an overpayment is rejected
# ---------------------------------------------------------------------------


def test_overpayment_is_rejected_and_the_due_is_unchanged(
    client: TestClient, test_db_session: Session
):
    """T20: paying more than the due is a 422 and changes nothing."""
    token = _login(client, test_db_session, "staff_overpay", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Over Payer")

    _credit_sale(client, token, rice, customer, quantity="2.000")  # 120.00 due

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "500.00"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "OVERPAYMENT_NOT_ALLOWED"
    assert "120.00" in response.json()["error"]["message"]

    due = client.get(f"/api/v1/customers/{customer.id}/due", headers=_auth(token))
    assert due.json()["current_due"] == "120.00"
    assert due.json()["payment_count"] == 0


# ---------------------------------------------------------------------------
# T21 - the amount must be positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["0.00", "-50.00"])
def test_non_positive_payment_amount_is_rejected(
    client: TestClient, test_db_session: Session, amount: str
):
    """T21: a zero or negative payment amount is a 422."""
    token = _login(client, test_db_session, f"staff_amount_{amount[:2]}", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Amount Customer")

    _credit_sale(client, token, rice, customer, quantity="1.000")

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": amount},
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# T22 - an inactive customer cannot pay
# ---------------------------------------------------------------------------


def test_payment_for_inactive_customer_is_rejected(
    client: TestClient, test_db_session: Session
):
    """T22: a payment for an inactive customer is a 422."""
    token = _login(client, test_db_session, "staff_inactive_pay", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Inactive Payer")

    _credit_sale(client, token, rice, customer, quantity="1.000")
    customer.is_active = False
    test_db_session.commit()

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "10.00"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "CUSTOMER_INACTIVE"


# ---------------------------------------------------------------------------
# T23 - a missing customer is a 404
# ---------------------------------------------------------------------------


def test_payment_for_missing_customer_returns_404(
    client: TestClient, test_db_session: Session
):
    """T23: a payment for a customer that does not exist is a 404."""
    token = _login(client, test_db_session, "staff_nocust_pay", "staff")

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": 999999, "amount": "10.00"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"


# ---------------------------------------------------------------------------
# T24 - the payment history, newest first
# ---------------------------------------------------------------------------


def test_payment_history_is_returned_newest_first(
    client: TestClient, test_db_session: Session
):
    """T24: the history endpoint lists the payments newest first."""
    token = _login(client, test_db_session, "staff_history", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "History Customer")

    _credit_sale(client, token, rice, customer, quantity="10.000")  # 600.00 due

    for amount in ("100.00", "200.00", "50.00"):
        response = client.post(
            "/api/v1/payments",
            headers=_auth(token),
            json={"customer_id": customer.id, "amount": amount},
        )
        assert response.status_code == 201, response.text

    history = client.get(
        f"/api/v1/payments?customer_id={customer.id}",
        headers=_auth(token),
    )
    assert history.status_code == 200, history.text
    data = history.json()
    assert data["total"] == 3
    amounts = [item["amount"] for item in data["items"]]
    assert amounts == ["50.00", "200.00", "100.00"]


# ---------------------------------------------------------------------------
# T25 - the due endpoint
# ---------------------------------------------------------------------------


def test_due_endpoint_lists_customers_with_a_due_only(
    client: TestClient, test_db_session: Session
):
    """T25: customers without credit sales and without payments are omitted."""
    token = _login(client, test_db_session, "staff_dues", "staff")
    rice = _make_product(test_db_session, "Rice", "1000.000", sale_price="60.00")

    owing = _make_customer(test_db_session, "Owing Customer")
    also_owing = _make_customer(test_db_session, "Also Owing")
    clean = _make_customer(test_db_session, "Clean Customer")

    _credit_sale(client, token, rice, owing, quantity="5.000")  # 300.00
    _credit_sale(client, token, rice, also_owing, quantity="10.000")  # 600.00

    response = client.get("/api/v1/customers/due", headers=_auth(token))
    assert response.status_code == 200, response.text
    data = response.json()

    names = [item["customer_name"] for item in data["items"]]
    assert "Clean Customer" not in names
    assert set(names) == {"Owing Customer", "Also Owing"}
    assert data["total"] == 2
    assert data["total_due_amount"] == "900.00"

    # Largest due first.
    assert data["items"][0]["customer_name"] == "Also Owing"
    assert data["items"][0]["current_due"] == "600.00"
    assert data["items"][1]["current_due"] == "300.00"
    assert clean.id not in [item["customer_id"] for item in data["items"]]


def test_due_endpoint_requires_authentication(client: TestClient):
    """T25: the due list is not public."""
    response = client.get("/api/v1/customers/due")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_due_breakdown_for_missing_customer_returns_404(
    client: TestClient, test_db_session: Session
):
    """The breakdown of a customer that does not exist is a 404."""
    token = _login(client, test_db_session, "staff_dues_404", "staff")

    response = client.get("/api/v1/customers/999999/due", headers=_auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"


# ---------------------------------------------------------------------------
# T26 - the audit log
# ---------------------------------------------------------------------------


def test_payment_writes_an_audit_entry(client: TestClient, test_db_session: Session):
    """T26: recording a payment writes a ``payment`` audit row."""
    token = _login(client, test_db_session, "staff_audit_pay", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Audit Customer")

    _credit_sale(client, token, rice, customer, quantity="2.000")  # 120.00 due

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={
            "customer_id": customer.id,
            "amount": "50.00",
            "payment_method": "nagad",
        },
    )
    assert response.status_code == 201, response.text
    payment_id = response.json()["id"]

    audit = (
        test_db_session.query(AuditLog)
        .filter(AuditLog.entity_type == "payment", AuditLog.entity_id == payment_id)
        .one()
    )
    assert audit.action == "create"
    assert audit.old_value is None
    assert audit.new_value["customer_id"] == customer.id
    assert audit.new_value["amount"] == "50.00"
    assert audit.new_value["payment_method"] == "nagad"
    assert audit.new_value["sale_id"] is None


# ---------------------------------------------------------------------------
# T27 - roles
# ---------------------------------------------------------------------------


def test_staff_may_record_a_payment(client: TestClient, test_db_session: Session):
    """T27: staff work the counter, so staff may take a payment."""
    token = _login(client, test_db_session, "staff_pay_allowed", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Counter Customer")

    _credit_sale(client, token, rice, customer, quantity="1.000")

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "10.00"},
    )
    assert response.status_code == 201, response.text


def test_unauthenticated_payment_request_returns_401(
    client: TestClient, test_db_session: Session
):
    """T27: an unauthenticated payment request is a 401."""
    customer = _make_customer(test_db_session, "No Token Customer")

    response = client.post(
        "/api/v1/payments",
        json={"customer_id": customer.id, "amount": "10.00"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_viewer_cannot_read_or_record_payments(
    client: TestClient, test_db_session: Session
):
    """A viewer is forbidden: only owner and staff work the counter."""
    viewer_token = _login(client, test_db_session, "viewer_payment", "viewer")
    owner_token = _login(client, test_db_session, "owner_for_viewer", "owner")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "Viewer Due Customer")

    # The sale itself is recorded by an owner so there is a due to read.
    _credit_sale(client, owner_token, rice, customer, quantity="1.000")

    recorded = client.post(
        "/api/v1/payments",
        headers=_auth(viewer_token),
        json={"customer_id": customer.id, "amount": "10.00"},
    )
    assert recorded.status_code == 403
    assert recorded.json()["error"]["code"] == "FORBIDDEN"

    history = client.get(
        f"/api/v1/payments?customer_id={customer.id}",
        headers=_auth(viewer_token),
    )
    assert history.status_code == 403
    assert history.json()["error"]["code"] == "FORBIDDEN"

    dues = client.get("/api/v1/customers/due", headers=_auth(viewer_token))
    assert dues.status_code == 403
    assert dues.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Extra: a payment tied to a specific sale
# ---------------------------------------------------------------------------


def test_payment_can_be_tied_to_one_sale(client: TestClient, test_db_session: Session):
    """A payment may name the credit sale it settles."""
    token = _login(client, test_db_session, "staff_tied", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Tied Customer")

    sale_id = _credit_sale(client, token, rice, customer, quantity="2.000")

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "120.00", "sale_id": sale_id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["sale_id"] == sale_id

    due = client.get(f"/api/v1/customers/{customer.id}/due", headers=_auth(token))
    assert due.json()["current_due"] == "0.00"


def test_payment_for_missing_sale_returns_404(
    client: TestClient, test_db_session: Session
):
    """A payment that names a sale that does not exist is a 404."""
    token = _login(client, test_db_session, "staff_nosale", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000")
    customer = _make_customer(test_db_session, "No Sale Customer")

    _credit_sale(client, token, rice, customer, quantity="1.000")

    response = client.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={"customer_id": customer.id, "amount": "10.00", "sale_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SALE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Concurrency: the overpayment check must hold under parallel requests
# ---------------------------------------------------------------------------


def test_two_concurrent_payments_cannot_both_pass_the_overpayment_check(
    test_db_session: Session,
):
    """R17 must hold when two payments are taken at the same moment.

    The customer row is locked while the due is read, so the second request
    waits and then sees the first payment. Without that lock both requests
    would read the same due and both would be accepted, letting a customer
    be paid twice what they owe.
    """
    from app.models.payment import Payment
    from app.services import payment_service

    token = _login_standalone(test_db_session, "staff_concurrent", "staff")
    rice = _make_product(test_db_session, "Rice", "100.000", sale_price="60.00")
    customer = _make_customer(test_db_session, "Concurrent Customer")

    # A credit sale of 600.00 leaves a due of exactly 600.00.
    _credit_sale_standalone(test_db_session, rice, customer, "10.000")

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
            payment_service.record_payment(
                db,
                PaymentCreate(customer_id=customer.id, amount=Decimal("600.00")),
                user_id=_user_id(test_db_session, "staff_concurrent"),
            )
            result = "SUCCESS"
        except HTTPException as exc:
            result = exc.detail["code"] if isinstance(exc.detail, dict) else str(exc.detail)
        finally:
            db.close()
        with lock:
            outcomes.append(result)

    def run() -> None:
        # Both threads reach the due check before either writes, so the lock
        # is what decides the outcome.
        barrier.wait(timeout=10)
        attempt()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(outcomes) == ["OVERPAYMENT_NOT_ALLOWED", "SUCCESS"]
    # Only one payment may exist and the customer may not be overpaid.
    payments = test_db_session.query(Payment).all()
    assert len(payments) == 1
    assert payments[0].amount == Decimal("600.00")
