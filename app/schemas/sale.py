"""Request and response schemas for sales.

Owner: Zahid. Module 2. Field names follow the ``sales`` and ``sale_items``
tables in ``docs/schema.md`` sections 3.11 and 3.12.

Quantity is ``NUMERIC(12,3)`` and money is ``NUMERIC(12,2)``. Both are
``Decimal`` only, never ``float``, and are serialised as JSON strings rounded
half-up.

The server is the only authority on totals: ``line_total`` and
``total_amount`` are computed from ``quantity * unit_price``. A client may send
``total_amount`` as a cross-check; a mismatch is rejected by the service.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

MAX_ITEMS_PER_SALE = 100

TotalAmount = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
PaidAmount = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
SaleNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]

PaymentType = Literal["cash", "credit"]


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


def _quantity(value: Decimal) -> str:
    return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class SaleItemIn(BaseModel):
    """One product line on a new sale."""

    model_config = ConfigDict(extra="forbid")

    product_id: Annotated[int, Field(gt=0)]
    # The positivity and the non-negative price are checked by the service so
    # it can answer with the documented codes.
    quantity: Annotated[Decimal, Field(max_digits=12, decimal_places=3)]
    # Omitted means "use the product's current sale_price".
    unit_price: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = None


class SaleCreate(BaseModel):
    """Body for recording a sale.

    ``paid_amount`` is required. For a cash sale it must equal the total the
    server computes (R5); for a credit sale it is the part paid at the
    counter and may be ``0`` (R7). The bound is checked by the service so it
    can answer with the documented ``INVALID_PAID_AMOUNT`` code.
    """

    model_config = ConfigDict(extra="forbid")

    # ``None`` is a walk-in cash sale with no customer record.
    customer_id: Annotated[int, Field(gt=0)] | None = None
    payment_type: PaymentType
    # The minimum length is checked by the service so it can answer with the
    # documented ``INVALID_SALE_ITEMS`` code instead of a generic one.
    items: Annotated[list[SaleItemIn], Field(max_length=MAX_ITEMS_PER_SALE)]
    paid_amount: PaidAmount
    note: SaleNote | None = None
    # Optional: the server computes the total and cross-checks this value.
    total_amount: TotalAmount | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SaleItemOut(BaseModel):
    """One product line on a recorded sale."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str | None = None
    unit: str | None = None
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    @field_serializer("quantity")
    def _serialize_quantity(self, value: Decimal) -> str:
        return _quantity(value)

    @field_serializer("unit_price", "line_total")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class SalePaymentOut(BaseModel):
    """A payment that settles this sale."""

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


class SaleSummaryOut(BaseModel):
    """A sale without its lines, used in lists."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int | None
    customer_name: str | None = None
    user_id: int | None
    payment_type: str
    total_amount: Decimal
    paid_amount: Decimal
    due_amount: Decimal
    item_count: int = 0
    note: str | None
    created_at: datetime

    @field_serializer("total_amount", "paid_amount", "due_amount")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class SaleOut(SaleSummaryOut):
    """A full sale with all of its lines and payments."""

    items: list[SaleItemOut] = Field(default_factory=list)
    payments: list[SalePaymentOut] = Field(default_factory=list)


class SaleListOut(BaseModel):
    """List of sales in the shared ``items`` / ``total`` shape."""

    items: list[SaleOut]
    total: int
