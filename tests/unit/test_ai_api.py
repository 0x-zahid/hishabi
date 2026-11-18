"""Unit tests for the AI Bangla entry endpoints.

Owner: Zahid. Module 3.

The AI provider is always mocked, so the suite never calls a real AI API and
never needs an API key to run.

Tests cover:
- The parse endpoint answers with a proposal and creates one log row.
- A proposal with a missing required field is a 422.
- The daily limit answers 429 and the provider is never called.
- The daily limit is per user.
- A provider error answers 503 and saves nothing.
- The fallback path works with no AI key set at all.
- The confirm endpoint creates exactly one sale through the sale service.
- Confirming twice answers 409 and creates no second sale.
- The reject endpoint saves nothing.
- A user cannot read another user's request.
"""

import json
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.sales import router as sales_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.ai_request_log import AIRequestLog
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.services import ai_provider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with the auth, sales and AI routers."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(sales_router)
    app.include_router(ai_router)

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


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch):
    """Replace the provider call with a canned answer."""
    state = {
        "response": json.dumps(
            {
                "customer_name": "Rahim",
                "items": [
                    {"product_name": "Rice 5kg", "quantity": 2, "unit_price": 250}
                ],
                "payment_type": "cash",
                "paid_amount": 500,
                "total_amount": 500,
            }
        ),
        "error": None,
        "calls": 0,
    }

    def _call_model(text: str) -> str:
        state["calls"] += 1
        if state["error"] is not None:
            raise state["error"]
        return state["response"]

    monkeypatch.setattr(ai_provider, "call_model", _call_model)
    return state


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
        role = db.query(Role).filter(Role.name == role_name).first()
        if role is None:
            role = Role(name=role_name, description=f"{role_name} role")
            db.add(role)
            db.commit()
            db.refresh(role)
        user.role_id = role.id
        db.commit()

    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _make_product(db: Session, name: str, stock: str = "100.000") -> Product:
    product = Product(
        category_id=None,
        name=name,
        unit="kg",
        purchase_price=Decimal("200.00"),
        sale_price=Decimal("250.00"),
        current_stock=Decimal(stock),
        low_stock_threshold=Decimal("5.000"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _make_customer(db: Session, name: str) -> Customer:
    customer = Customer(name=name, phone=None, is_active=True)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse(client: TestClient, token: str, text: str = "রহিম ভাই ৫ কেজি চাল নিয়েছে"):
    return client.post("/api/v1/ai/parse", headers=_auth(token), json={"text": text})


# ---------------------------------------------------------------------------
# T1 - a Bangla sentence produces a proposal
# ---------------------------------------------------------------------------


def test_parse_returns_a_proposal_and_creates_one_log_row(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T1: the parse endpoint answers 200 with a proposal and logs the request."""
    token = _login(client, test_db_session, "ai_parse_ok", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg")

    response = _parse(client, token)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["request_id"] > 0
    assert data["status"] == "success"
    assert data["proposal"]["customer"]["id"] == customer.id
    assert data["proposal"]["customer"]["matched"] is True
    assert data["proposal"]["customer"]["warning"] is None
    assert data["proposal"]["items"][0]["product"]["id"] == product.id
    assert data["proposal"]["items"][0]["quantity"] == "2.000"
    assert data["proposal"]["items"][0]["unit_price"] == "250.00"
    assert data["proposal"]["items"][0]["flags"] == []
    assert data["proposal"]["payment_type"] == "cash"
    assert data["proposal"]["paid_amount"] == "500.00"
    assert data["proposal"]["total_amount"] == "500.00"
    assert data["proposal"]["flags"] == []
    assert data["warnings"] == []
    assert data["remaining_requests_today"] == 19

    # Exactly one log row (R16).
    rows = test_db_session.query(AIRequestLog).all()
    assert len(rows) == 1
    assert rows[0].status == "success"
    assert rows[0].confirmed is False
    assert rows[0].input_text == "রহিম ভাই ৫ কেজি চাল নিয়েছে"

    # Nothing was saved to the sales table (R12).
    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T2 - a missing required field is a 422
# ---------------------------------------------------------------------------


def test_parse_with_a_missing_required_field_returns_422(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T2: an answer that does not match the fixed shape is a 422."""
    token = _login(client, test_db_session, "ai_parse_bad", "staff")
    fake_provider["response"] = json.dumps(
        {"customer_name": "Rahim", "payment_type": "cash", "total_amount": 500}
    )

    response = _parse(client, token)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "INVALID_AI_RESPONSE"
    # The message names the invalid field.
    assert "items" in body["error"]["message"]

    assert test_db_session.query(Sale).count() == 0


# ---------------------------------------------------------------------------
# T3 - the daily limit
# ---------------------------------------------------------------------------


def test_the_daily_limit_returns_429_and_the_provider_is_not_called(
    client: TestClient, test_db_session: Session, fake_provider, monkeypatch
):
    """T3: at the limit the answer is 429 and the provider is never called."""
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 2)
    token = _login(client, test_db_session, "ai_limit", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    assert _parse(client, token).status_code == 200
    assert _parse(client, token).status_code == 200
    calls_before = fake_provider["calls"]
    assert calls_before == 2

    response = _parse(client, token)
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "AI_DAILY_LIMIT_REACHED"
    # The provider was not called a third time.
    assert fake_provider["calls"] == calls_before
    assert test_db_session.query(Sale).count() == 0


def test_the_daily_limit_is_per_user(
    client: TestClient, test_db_session: Session, fake_provider, monkeypatch
):
    """T3: one user hitting the limit does not affect another user."""
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 1)
    first_token = _login(client, test_db_session, "ai_limit_one", "staff")
    second_token = _login(client, test_db_session, "ai_limit_two", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    assert _parse(client, first_token).status_code == 200
    assert _parse(client, first_token).status_code == 429

    # The second user still has their own request.
    assert _parse(client, second_token).status_code == 200


def test_the_usage_endpoint_reports_the_remaining_requests(
    client: TestClient, test_db_session: Session, fake_provider
):
    """The usage endpoint answers with the used, limit and remaining counts."""
    token = _login(client, test_db_session, "ai_usage", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    before = client.get("/api/v1/ai/requests/today", headers=_auth(token))
    assert before.status_code == 200, before.text
    assert before.json() == {"used": 0, "limit": 20, "remaining": 20}

    _parse(client, token)

    after = client.get("/api/v1/ai/requests/today", headers=_auth(token))
    assert after.json() == {"used": 1, "limit": 20, "remaining": 19}


# ---------------------------------------------------------------------------
# T4 - the provider fails
# ---------------------------------------------------------------------------


def test_a_provider_error_returns_503_and_saves_nothing(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T4: a provider outage is a 503 with the manual-entry flag."""
    token = _login(client, test_db_session, "ai_provider_down", "staff")
    fake_provider["error"] = ai_provider.AIProviderError(
        "The AI service could not be reached.",
        detail="TimeoutError: the provider did not answer",
    )

    response = _parse(client, token)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"]["code"] == "AI_SERVICE_UNAVAILABLE"
    # The client is told to fall back to the manual form.
    assert body["error"]["use_manual_entry"] is True
    # The raw provider error never reaches the client.
    assert "TimeoutError" not in body["error"]["message"]

    assert test_db_session.query(Sale).count() == 0
    assert test_db_session.query(SaleItem).count() == 0
    assert test_db_session.query(StockMovement).count() == 0
    rows = test_db_session.query(AIRequestLog).all()
    assert len(rows) == 1
    assert rows[0].status == "provider_error"


def test_an_unparseable_response_returns_503_and_saves_nothing(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T4: prose instead of JSON is a 503 and nothing is saved."""
    token = _login(client, test_db_session, "ai_parse_fail", "staff")
    fake_provider["response"] = "আমি বুঝতে পারছি না।"

    response = _parse(client, token)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["use_manual_entry"] is True

    assert test_db_session.query(Sale).count() == 0
    rows = test_db_session.query(AIRequestLog).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"


def test_the_manual_path_works_with_no_ai_key(
    client: TestClient, test_db_session: Session, monkeypatch
):
    """T4: with no key at all the manual form path still records a sale.

    The manual form posts to the ordinary sale endpoint, which never touches
    the AI provider, so a sale can be recorded while the AI is unavailable.
    """
    from app.services import ai_provider as provider

    monkeypatch.setattr(provider.settings, "AI_API_KEY", "")
    monkeypatch.setattr(provider, "is_configured", lambda: False)

    token = _login(client, test_db_session, "ai_manual", "staff")
    product = _make_product(test_db_session, "Rice 5kg")

    # The AI endpoint refuses and asks for the manual form.
    ai_response = _parse(client, token)
    assert ai_response.status_code == 503, ai_response.text
    assert ai_response.json()["error"]["use_manual_entry"] is True

    # The manual form posts straight to the sale endpoint.
    manual_response = client.post(
        "/api/v1/sales",
        headers=_auth(token),
        json={
            "payment_type": "cash",
            "items": [{"product_id": product.id, "quantity": "2.000"}],
            "paid_amount": "500.00",
        },
    )
    assert manual_response.status_code == 201, manual_response.text
    assert test_db_session.query(Sale).count() == 1


# ---------------------------------------------------------------------------
# T5 - confirm
# ---------------------------------------------------------------------------


def test_confirm_creates_exactly_one_sale(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T5: confirming a proposal records one sale through the sale service."""
    token = _login(client, test_db_session, "ai_confirm", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg")

    parsed = _parse(client, token)
    assert parsed.status_code == 200, parsed.text
    request_id = parsed.json()["request_id"]

    response = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            "customer": {"id": customer.id, "name": "Rahim"},
            "items": [
                {"product": {"id": product.id, "name": "Rice 5kg"}, "quantity": "2.000", "unit_price": "250.00"}
            ],
            "payment_type": "cash",
            "paid_amount": "500.00",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()

    # The answer has the same shape as the existing sale endpoint.
    assert data["id"] > 0
    assert data["customer_id"] == customer.id
    assert data["payment_type"] == "cash"
    assert data["total_amount"] == "500.00"
    assert data["paid_amount"] == "500.00"
    assert data["due_amount"] == "0.00"
    assert len(data["items"]) == 1

    assert test_db_session.query(Sale).count() == 1
    # The sale went through the existing sale service, so the stock and the
    # ledger moved too.
    assert test_db_session.query(StockMovement).count() == 1

    # The log row is marked as confirmed.
    row = test_db_session.query(AIRequestLog).filter(AIRequestLog.id == request_id).one()
    assert row.confirmed is True


def test_confirm_writes_an_audit_log_entry(
    client: TestClient, test_db_session: Session, fake_provider
):
    """R15: a confirmed proposal writes an audit row."""
    token = _login(client, test_db_session, "ai_audit", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, token).json()["request_id"]
    response = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            "customer": {"id": customer.id, "name": "Rahim"},
            "items": [
                {"product": {"id": product.id, "name": "Rice 5kg"}, "quantity": "2.000", "unit_price": "250.00"}
            ],
            "payment_type": "cash",
            "paid_amount": "500.00",
        },
    )
    assert response.status_code == 201, response.text

    # The sale service writes its own sale row, and the AI confirmation writes
    # its own row for the confirmed request.
    entries = (
        test_db_session.query(AuditLog)
        .filter(AuditLog.entity_type == "ai_request_log")
        .all()
    )
    assert len(entries) == 1
    assert entries[0].action == "confirm"
    assert entries[0].entity_id == request_id
    assert entries[0].new_value["total_amount"] == "500.00"
    assert entries[0].new_value["items"][0]["product_id"] == product.id

    sale_entries = (
        test_db_session.query(AuditLog).filter(AuditLog.entity_type == "sale").all()
    )
    assert len(sale_entries) == 1


def test_confirming_twice_returns_409_and_creates_no_second_sale(
    client: TestClient, test_db_session: Session, fake_provider
):
    """R14: confirming the same proposal twice does not create two sales."""
    token = _login(client, test_db_session, "ai_twice", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, token).json()["request_id"]
    body = {
        "customer": {"id": customer.id, "name": "Rahim"},
        "items": [
            {"product": {"id": product.id, "name": "Rice 5kg"}, "quantity": "2.000", "unit_price": "250.00"}
        ],
        "payment_type": "cash",
        "paid_amount": "500.00",
    }

    first = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm", headers=_auth(token), json=body
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm", headers=_auth(token), json=body
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "AI_REQUEST_ALREADY_CONFIRMED"

    assert test_db_session.query(Sale).count() == 1
    assert test_db_session.query(StockMovement).count() == 1


def test_confirming_an_invalid_edited_proposal_returns_422(
    client: TestClient, test_db_session: Session, fake_provider
):
    """R13: the edited proposal is re-validated before the sale is created."""
    token = _login(client, test_db_session, "ai_invalid_edit", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, token).json()["request_id"]

    # A quantity of zero is still invalid after the user edited it.
    response = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            "customer": {"id": customer.id, "name": "Rahim"},
            "items": [
                {"product": {"id": product.id, "name": "Rice 5kg"}, "quantity": "0.000", "unit_price": "250.00"}
            ],
            "payment_type": "cash",
            "paid_amount": "0.00",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_QUANTITY"
    assert test_db_session.query(Sale).count() == 0


def test_every_field_can_be_edited_before_confirming(
    client: TestClient, test_db_session: Session, fake_provider
):
    """The user may change the customer, the items, the price and the payment.

    The edited values, not the ones the AI proposed, are what reaches the
    sale table.
    """
    token = _login(client, test_db_session, "ai_edit_all", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    other_customer = _make_customer(test_db_session, "Karim")
    rice = _make_product(test_db_session, "Rice 5kg")
    oil = _make_product(test_db_session, "Oil 1L")

    request_id = _parse(client, token).json()["request_id"]

    response = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            # The customer was changed.
            "customer": {"id": other_customer.id, "name": "Karim"},
            # The product, the quantity and the price were all changed.
            "items": [
                {
                    "product": {"id": oil.id, "name": "Oil 1L"},
                    "quantity": "3.000",
                    "unit_price": "100.00",
                }
            ],
            # The payment type was changed to credit.
            "payment_type": "credit",
            "paid_amount": "50.00",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["customer_id"] == other_customer.id
    assert data["customer_name"] == "Karim"
    assert data["payment_type"] == "credit"
    # The total is the edited one: 3 * 100.
    assert data["total_amount"] == "300.00"
    assert data["paid_amount"] == "50.00"
    assert data["due_amount"] == "250.00"
    assert len(data["items"]) == 1
    assert data["items"][0]["product_id"] == oil.id
    assert data["items"][0]["quantity"] == "3.000"
    assert data["items"][0]["unit_price"] == "100.00"

    # The stock that moved is the edited product, not the proposed one.
    assert test_db_session.query(Sale).count() == 1
    assert test_db_session.query(StockMovement).count() == 1
    movement = test_db_session.query(StockMovement).one()
    assert movement.product_id == oil.id
    assert movement.quantity == Decimal("3.000")


def test_a_failed_confirmation_leaves_the_request_open_for_a_retry(
    client: TestClient, test_db_session: Session, fake_provider
):
    """A confirmation that the sale service refuses does not close the request.

    The row is marked confirmed inside the same transaction as the sale, so a
    rollback takes the mark with it and the user can fix the proposal and
    try again.
    """
    token = _login(client, test_db_session, "ai_retry", "staff")
    customer = _make_customer(test_db_session, "Rahim")
    product = _make_product(test_db_session, "Rice 5kg", stock="1.000")

    request_id = _parse(client, token).json()["request_id"]

    # More than the stock on hand: the sale service refuses with 409.
    refused = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            "customer": {"id": customer.id, "name": "Rahim"},
            "items": [
                {
                    "product": {"id": product.id, "name": "Rice 5kg"},
                    "quantity": "25.000",
                    "unit_price": "250.00",
                }
            ],
            "payment_type": "cash",
            "paid_amount": "6250.00",
        },
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert test_db_session.query(Sale).count() == 0

    # The request is still open and can be confirmed with a corrected quantity.
    row = (
        test_db_session.query(AIRequestLog)
        .filter(AIRequestLog.id == request_id)
        .one()
    )
    assert row.confirmed is False

    retried = client.post(
        f"/api/v1/ai/requests/{request_id}/confirm",
        headers=_auth(token),
        json={
            "customer": {"id": customer.id, "name": "Rahim"},
            "items": [
                {
                    "product": {"id": product.id, "name": "Rice 5kg"},
                    "quantity": "1.000",
                    "unit_price": "250.00",
                }
            ],
            "payment_type": "cash",
            "paid_amount": "250.00",
        },
    )
    assert retried.status_code == 201, retried.text
    assert test_db_session.query(Sale).count() == 1

    row = (
        test_db_session.query(AIRequestLog)
        .filter(AIRequestLog.id == request_id)
        .one()
    )
    assert row.confirmed is True


# ---------------------------------------------------------------------------
# T6 - reject
# ---------------------------------------------------------------------------

def test_the_reject_endpoint_saves_nothing(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T6: rejecting a proposal creates no sale and no other row."""
    token = _login(client, test_db_session, "ai_reject", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, token).json()["request_id"]

    response = client.post(
        f"/api/v1/ai/requests/{request_id}/reject", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert "discarded" in response.json()["message"]

    assert test_db_session.query(Sale).count() == 0
    assert test_db_session.query(StockMovement).count() == 0
    assert test_db_session.query(AuditLog).count() == 0


# ---------------------------------------------------------------------------
# T7 - reading a request
# ---------------------------------------------------------------------------


def test_a_user_cannot_read_another_users_request(
    client: TestClient, test_db_session: Session, fake_provider
):
    """T7: another user's request is reported as missing."""
    first_token = _login(client, test_db_session, "ai_owner_of_request", "staff")
    second_token = _login(client, test_db_session, "ai_other_reader", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, first_token).json()["request_id"]

    response = client.get(
        f"/api/v1/ai/requests/{request_id}", headers=_auth(second_token)
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "AI_REQUEST_NOT_FOUND"


def test_a_user_can_read_their_own_request(
    client: TestClient, test_db_session: Session, fake_provider
):
    """The owner of a request reads their own proposal back."""
    token = _login(client, test_db_session, "ai_reader", "staff")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    request_id = _parse(client, token).json()["request_id"]

    response = client.get(f"/api/v1/ai/requests/{request_id}", headers=_auth(token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["request_id"] == request_id
    assert data["status"] == "success"
    assert data["confirmed"] is False
    assert data["proposal"]["customer"]["matched"] is True
    assert data["proposal"]["total_amount"] == "500.00"


# ---------------------------------------------------------------------------
# T8 - authentication and roles
# ---------------------------------------------------------------------------


def test_an_unauthenticated_parse_request_returns_401(
    client: TestClient, test_db_session: Session, fake_provider
):
    """R1: every endpoint needs an authenticated user."""
    response = client.post("/api/v1/ai/parse", json={"text": "চাল নিয়েছে"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert fake_provider["calls"] == 0


def test_an_owner_may_use_ai_entry(client: TestClient, test_db_session: Session, fake_provider):
    """R1: the owner may use AI entry."""
    token = _login(client, test_db_session, "ai_owner", "owner")
    _make_customer(test_db_session, "Rahim")
    _make_product(test_db_session, "Rice 5kg")

    assert _parse(client, token).status_code == 200


def test_a_viewer_may_not_use_ai_entry(
    client: TestClient, test_db_session: Session, fake_provider
):
    """R1: only the owner and staff may use AI entry."""
    token = _login(client, test_db_session, "ai_viewer", "viewer")

    response = _parse(client, token)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert fake_provider["calls"] == 0
