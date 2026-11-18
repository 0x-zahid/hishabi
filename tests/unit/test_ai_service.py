"""Unit tests for the AI Bangla entry logic.

Owner: Zahid. Module 3.

The AI provider is always mocked, so the suite never calls a real AI API and
never needs an API key to run.

Tests cover:
- The fixed JSON shape parses into a valid proposal.
- A missing required field is rejected.
- An unknown customer name returns the proposal with an unmatched customer
  and suggestions, not an error.
- An unknown product name returns the proposal with an unmatched product and
  suggestions.
- An inactive customer produces a warning, not a rejection.
- A quantity of zero or a negative quantity is flagged.
- A negative unit price is flagged.
- The AI's total_amount is ignored and the server-computed total is used.
- A customer name is matched case-insensitively, ignoring whitespace.
- The daily limit blocks the call, and the provider is never called.
- The daily limit counts per user, so a second user is not affected.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ai_request_log import (
    STATUS_FAILED,
    STATUS_PROVIDER_ERROR,
    STATUS_QUOTA_EXCEEDED,
    STATUS_SUCCESS,
    AIRequestLog,
)
from app.models.customer import Customer
from app.models.product import Product
from app.models.role import Role
from app.models.user import User
from app.schemas.ai import AIExtractedData
from app.services import ai_provider, ai_service


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db(test_db_session: Session) -> Session:
    """A short alias for the project's shared test session fixture."""
    return test_db_session


@pytest.fixture
def user(db: Session) -> User:
    """A user who may use AI entry."""
    role = db.query(Role).filter(Role.name == "staff").first()
    if role is None:
        role = Role(name="staff", description="staff role")
        db.add(role)
        db.commit()
        db.refresh(role)

    row = User(
        full_name="AI Tester",
        username="ai_tester",
        email="ai_tester@example.com",
        password_hash="not-used-here",
        is_active=True,
        role_id=role.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def other_user(db: Session) -> User:
    """A second user, used to prove the daily limit is per user."""
    role = db.query(Role).filter(Role.name == "staff").first()
    row = User(
        full_name="Other Tester",
        username="ai_other_tester",
        email="ai_other_tester@example.com",
        password_hash="not-used-here",
        is_active=True,
        role_id=role.id if role else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def customer(db: Session) -> Customer:
    """An active customer named Rahim."""
    row = Customer(name="Rahim", phone=None, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def inactive_customer(db: Session) -> Customer:
    """A deactivated customer."""
    row = Customer(name="Old Rahim", phone=None, is_active=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def product(db: Session) -> Product:
    """An active product called Rice 5kg."""
    row = Product(
        category_id=None,
        name="Rice 5kg",
        unit="kg",
        purchase_price=Decimal("200.00"),
        sale_price=Decimal("250.00"),
        current_stock=Decimal("100.000"),
        low_stock_threshold=Decimal("5.000"),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _valid_ai_json(**overrides) -> dict:
    """Return the fixed JSON shape with the given keys replaced."""
    data = {
        "customer_name": "Rahim",
        "items": [{"product_name": "Rice 5kg", "quantity": 2, "unit_price": 250}],
        "payment_type": "cash",
        "paid_amount": 500,
        "total_amount": 500,
    }
    data.update(overrides)
    return data


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch):
    """Replace the provider call with a canned answer.

    The returned callable lets a test change the answer or make the provider
    fail.
    """
    import json

    state = {"response": json.dumps(_valid_ai_json()), "error": None, "calls": 0}

    def _call_model(text: str) -> str:
        state["calls"] += 1
        if state["error"] is not None:
            raise state["error"]
        return state["response"]

    monkeypatch.setattr(ai_provider, "call_model", _call_model)
    return state


# ---------------------------------------------------------------------------
# The fixed JSON shape
# ---------------------------------------------------------------------------


def test_the_fixed_json_shape_parses_into_a_valid_proposal(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """The documented shape is accepted and produces a matched proposal."""
    row, proposal, warnings, remaining = ai_service.parse_sale_sentence(
        db, user.id, "রহিম ভাই ৫ কেজি চাল ২টা নিয়েছে ৫০০ টাকা দিয়েছে"
    )

    assert row.status == STATUS_SUCCESS
    assert proposal.customer.id == customer.id
    assert proposal.customer.matched is True
    assert proposal.customer.warning is None
    assert len(proposal.items) == 1
    assert proposal.items[0].product.id == product.id
    assert proposal.items[0].product.matched is True
    assert proposal.items[0].quantity == Decimal("2.000")
    assert proposal.items[0].unit_price == Decimal("250.00")
    assert proposal.items[0].flags == []
    assert proposal.payment_type == "cash"
    assert proposal.paid_amount == Decimal("500.00")
    assert proposal.total_amount == Decimal("500.00")
    assert proposal.flags == []
    assert warnings == []
    assert remaining == 19


def test_a_missing_required_field_is_rejected(
    db: Session, user: User, fake_provider
):
    """A proposal without ``items`` is refused and nothing is saved."""
    import json

    fake_provider["response"] = json.dumps(
        {"customer_name": "Rahim", "payment_type": "cash", "total_amount": 500}
    )

    with pytest.raises(HTTPException) as exc_info:
        ai_service.parse_sale_sentence(db, user.id, "রহিম ৫ কেজি চাল নিয়েছে")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "INVALID_AI_RESPONSE"
    # The message names the field that was wrong.
    assert "items" in exc_info.value.detail["message"]

    assert db.query(AIRequestLog).count() == 1
    assert db.query(AIRequestLog).one().status == STATUS_FAILED


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_an_unknown_customer_returns_the_proposal_with_suggestions(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """An unknown customer is not an error: the proposal comes back unmatched."""
    import json

    fake_provider["response"] = json.dumps(_valid_ai_json(customer_name="Rahim Uddin"))

    row, proposal, warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "রহিম উদ্দিন ৫ কেজি চাল নিয়েছে"
    )

    assert row.status == STATUS_SUCCESS
    assert proposal.customer.id is None
    assert proposal.customer.matched is False
    assert proposal.customer.name == "Rahim Uddin"
    assert "customer_not_matched" in proposal.flags

    customer_warnings = [w for w in warnings if w.field == "customer"]
    assert len(customer_warnings) == 1
    # The suggestion list names the closest customer in the database.
    assert [s.name for s in customer_warnings[0].suggestions] == ["Rahim"]


def test_an_unknown_product_returns_the_proposal_with_suggestions(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """An unknown product is returned as unmatched, with candidates."""
    import json

    fake_provider["response"] = json.dumps(
        _valid_ai_json(
            items=[{"product_name": "Rice 10kg", "quantity": 1, "unit_price": 500}]
        )
    )

    row, proposal, warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "১০ কেজি চাল নিয়েছে"
    )

    assert row.status == STATUS_SUCCESS
    assert proposal.items[0].product.id is None
    assert proposal.items[0].product.matched is False
    assert "product not matched" in proposal.items[0].flags

    product_warnings = [w for w in warnings if w.field == "items[0].product"]
    assert len(product_warnings) == 1
    assert [s.name for s in product_warnings[0].suggestions] == ["Rice 5kg"]


def test_an_inactive_customer_produces_a_warning_not_a_rejection(
    db: Session, user: User, inactive_customer: Customer, product: Product, fake_provider
):
    """An inactive customer still matches, but carries a warning (R9)."""
    import json

    fake_provider["response"] = json.dumps(_valid_ai_json(customer_name="Old Rahim"))

    row, proposal, warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "ওল্ড রহিম চাল নিয়েছে"
    )

    assert row.status == STATUS_SUCCESS
    assert proposal.customer.id == inactive_customer.id
    assert proposal.customer.matched is True
    assert proposal.customer.warning is not None
    assert "inactive" in proposal.customer.warning.lower()
    assert any(w.field == "customer" for w in warnings)


def test_a_matching_customer_name_is_found_case_insensitively_with_whitespace(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """Surrounding whitespace and a different case still match (R7)."""
    import json

    fake_provider["response"] = json.dumps(_valid_ai_json(customer_name="  rAhIm  "))

    _row, proposal, _warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "রহিম চাল নিয়েছে"
    )

    assert proposal.customer.id == customer.id
    assert proposal.customer.matched is True
    assert proposal.customer.name == "Rahim"


# ---------------------------------------------------------------------------
# Validation flags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -3])
def test_a_quantity_of_zero_or_less_is_flagged(
    db: Session, user: User, customer: Customer, product: Product, fake_provider, quantity
):
    """A bad quantity is flagged so the user can fix it (R10)."""
    import json

    fake_provider["response"] = json.dumps(
        _valid_ai_json(
            items=[{"product_name": "Rice 5kg", "quantity": quantity, "unit_price": 250}],
            paid_amount=0,
            total_amount=0,
        )
    )

    _row, proposal, _warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "চাল নিয়েছে"
    )

    assert proposal.items[0].flags == ["quantity must be greater than zero"]


def test_a_negative_unit_price_is_flagged(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """A negative price is flagged, not rejected (R10)."""
    import json

    fake_provider["response"] = json.dumps(
        _valid_ai_json(
            items=[{"product_name": "Rice 5kg", "quantity": 2, "unit_price": -50}],
            paid_amount=-100,
            total_amount=-100,
        )
    )

    _row, proposal, _warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "চাল নিয়েছে"
    )

    assert proposal.items[0].flags == ["unit_price cannot be negative"]
    # The total is still computed from the items, so the user sees the real
    # number once the price is corrected.
    assert proposal.total_amount == Decimal("-100.00")


# ---------------------------------------------------------------------------
# The total
# ---------------------------------------------------------------------------


def test_the_ai_total_is_ignored_and_the_server_total_is_used(
    db: Session, user: User, customer: Customer, product: Product, fake_provider
):
    """The server recomputes the total from the items (R11)."""
    import json

    fake_provider["response"] = json.dumps(
        _valid_ai_json(
            items=[
                {"product_name": "Rice 5kg", "quantity": 2, "unit_price": 250},
                {"product_name": "Rice 5kg", "quantity": 1, "unit_price": 100},
            ],
            paid_amount=600,
            total_amount=99999,
        )
    )

    _row, proposal, warnings, _remaining = ai_service.parse_sale_sentence(
        db, user.id, "চাল নিয়েছে"
    )

    # 2 * 250 + 1 * 100
    assert proposal.total_amount == Decimal("600.00")
    total_warnings = [w for w in warnings if w.field == "total_amount"]
    assert len(total_warnings) == 1
    assert "99999.00" in total_warnings[0].message


# ---------------------------------------------------------------------------
# The daily limit
# ---------------------------------------------------------------------------


def test_the_daily_limit_blocks_the_call_and_the_provider_is_never_called(
    db: Session, user: User, customer: Customer, product: Product, fake_provider, monkeypatch
):
    """At the limit the answer is 429 and the provider is not called (R2)."""
    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 2)

    for _ in range(2):
        ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    calls_before = fake_provider["calls"]
    assert calls_before == 2

    with pytest.raises(HTTPException) as exc_info:
        ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "AI_DAILY_LIMIT_REACHED"
    # The provider was not called again.
    assert fake_provider["calls"] == calls_before


def test_the_daily_limit_counts_per_user(
    db: Session,
    user: User,
    other_user: User,
    customer: Customer,
    product: Product,
    fake_provider,
    monkeypatch,
):
    """One user hitting the limit does not affect another user (R2)."""
    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 1)

    ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    with pytest.raises(HTTPException):
        ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    # The second user is not affected.
    row, _proposal, _warnings, remaining = ai_service.parse_sale_sentence(
        db, other_user.id, "চাল নিয়েছে"
    )
    assert row.status == STATUS_SUCCESS
    assert remaining == 0


def test_only_todays_requests_count_towards_the_limit(
    db: Session, user: User, fake_provider, monkeypatch
):
    """A request from yesterday does not use up today's limit."""
    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 2)

    yesterday = datetime.combine(date.today() - timedelta(days=1), time.min)
    db.add(
        AIRequestLog(
            user_id=user.id,
            input_text="পুরনো বাক্য",
            status=STATUS_SUCCESS,
            confirmed=False,
            created_at=yesterday,
        )
    )
    db.commit()

    assert ai_service.count_requests_today(db, user.id) == 0

    usage = ai_service.get_usage(db, user.id)
    assert usage == {"used": 0, "limit": 2, "remaining": 2}


def test_a_provider_error_saves_nothing(
    db: Session, user: User, fake_provider
):
    """A provider outage is logged and nothing else is written (R3)."""
    from app.models.sale import Sale

    fake_provider["error"] = ai_provider.AIProviderError(
        "The AI service could not be reached.",
        detail="TimeoutError: the provider did not answer",
    )

    with pytest.raises(HTTPException) as exc_info:
        ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "AI_SERVICE_UNAVAILABLE"
    # The client is told to use the manual form.
    assert exc_info.value.detail["use_manual_entry"] is True
    # The raw provider text is not leaked to the client.
    assert "TimeoutError" not in exc_info.value.detail["message"]

    assert db.query(Sale).count() == 0
    rows = db.query(AIRequestLog).all()
    assert len(rows) == 1
    assert rows[0].status == STATUS_PROVIDER_ERROR
    # The detail is kept server side.
    assert "TimeoutError" in rows[0].error_message


def test_an_unparseable_provider_response_saves_nothing(db: Session, user: User, fake_provider):
    """Prose instead of JSON is a failure, and nothing is saved (R3)."""
    from app.models.sale import Sale

    fake_provider["response"] = "আমি বুঝতে পারছি না, দুঃখিত।"

    with pytest.raises(HTTPException) as exc_info:
        ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "AI_SERVICE_UNAVAILABLE"
    assert exc_info.value.detail["use_manual_entry"] is True

    assert db.query(Sale).count() == 0
    rows = db.query(AIRequestLog).all()
    assert len(rows) == 1
    assert rows[0].status == STATUS_FAILED
    assert rows[0].ai_response == "আমি বুঝতে পারছি না, দুঃখিত।"


def test_a_blocked_request_is_logged_as_quota_exceeded(
    db: Session, user: User, fake_provider, monkeypatch
):
    """The refused attempt is recorded, so the limit cannot be probed for free."""
    monkeypatch.setattr(ai_service.settings, "AI_DAILY_LIMIT", 1)

    ai_service.parse_sale_sentence(db, user.id, "চাল নিয়েছে")
    with pytest.raises(HTTPException):
        ai_service.parse_sale_sentence(db, user.id, "আরেকটা চাল নিয়েছে")

    rows = db.query(AIRequestLog).all()
    assert len(rows) == 2
    assert rows[-1].status == STATUS_QUOTA_EXCEEDED
    # The blocked attempt does not count against the limit itself.
    assert ai_service.count_requests_today(db, user.id) == 1


# ---------------------------------------------------------------------------
# The extracted-data schema on its own
# ---------------------------------------------------------------------------


def test_the_extracted_data_schema_requires_items():
    """The schema refuses a body without the required keys."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        AIExtractedData.model_validate(
            {"customer_name": "Rahim", "payment_type": "cash", "total_amount": 500}
        )


def test_the_extracted_data_schema_rejects_an_unknown_payment_type():
    """``payment_type`` is limited to cash and credit."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        AIExtractedData.model_validate(
            {
                "items": [{"product_name": "চাল", "quantity": 1, "unit_price": 10}],
                "payment_type": "card",
                "total_amount": 10,
            }
        )
