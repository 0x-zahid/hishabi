"""Request and response schemas for customer payments and customer dues.

Owner: Zahid. Module 2. Field names follow the ``payments`` table in
``docs/schema.md`` section 3.13 and the breakdown returned by
``app/services/dues_service.py``.

Money is ``NUMERIC(12,2)`` and is handled as ``Decimal`` only, never
``float``. Amounts are serialised as JSON strings rounded half-up.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer

MONEY_PLACES = Decimal("0.01")

# The amount is checked by the service so it can answer with the documented
# ``INVALID_PAYMENT_AMOUNT`` code instead of a generic one.
PaymentAmount = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
PaymentMethod = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
PaymentNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class PaymentCreate(BaseModel):
    """Body for recording a payment against a customer's due."""

    model_config = ConfigDict(extra="forbid")

    customer_id: Annotated[int, Field(gt=0)]
    amount: PaymentAmount
    # The credit sale this payment settles, when it is tied to one sale.
    sale_id: Annotated[int, Field(gt=0)] | None = None
    payment_method: PaymentMethod | None = None
    note: PaymentNote | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PaymentOut(BaseModel):
    """Public representation of a recorded payment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_name: str | None = None
    user_id: int | None
    sale_id: int | None
    amount: Decimal
    payment_method: str | None
    note: str | None
    created_at: datetime

    @field_serializer("amount")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class PaymentListOut(BaseModel):
    """List of payments in the shared ``items`` / ``total`` shape."""

    items: list[PaymentOut]
    total: int


# ---------------------------------------------------------------------------
# Customer dues
# ---------------------------------------------------------------------------


class CustomerDueBreakdownOut(BaseModel):
    """How one customer's outstanding due was reached."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    total_credit_sales: Decimal
    total_paid: Decimal
    current_due: Decimal
    sale_count: int
    payment_count: int

    @field_serializer("total_credit_sales", "total_paid", "current_due")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class CustomerDueListItemOut(CustomerDueBreakdownOut):
    """One customer's due in the all-customers list."""

    customer_name: str
    phone: str | None = None


class CustomerDueListOut(BaseModel):
    """List of customers with a due, largest due first."""

    items: list[CustomerDueListItemOut]
    total: int
    total_due_amount: Decimal = Decimal("0.00")

    @field_serializer("total_due_amount")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)
