"""Request and response schemas for purchases from suppliers.

Owner: Azaz (237). Field names follow the ``purchases`` and ``purchase_items``
tables in ``docs/schema.md`` sections 3.9 and 3.10.

Quantity is ``NUMERIC(12,3)`` and money is ``NUMERIC(12,2)``. Both are
``Decimal`` only, never ``float``, and are serialised as JSON strings rounded
half-up.

The server is the only authority on totals: ``line_total`` and
``total_amount`` are computed from ``quantity * unit_cost``. A client may send
``total_amount`` as a cross-check; a mismatch is rejected by the service.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer, model_validator

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

MAX_ITEMS_PER_PURCHASE = 100

PurchaseQuantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
TotalAmount = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
InvoiceNo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
PurchaseNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


def _quantity(value: Decimal) -> str:
    return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class PurchaseItemIn(BaseModel):
    """One product line on a new purchase."""

    model_config = ConfigDict(extra="forbid")

    product_id: Annotated[int, Field(gt=0)]
    quantity: PurchaseQuantity
    unit_cost: UnitCost


class PurchaseCreate(BaseModel):
    """Body for recording a purchase from a supplier."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: Annotated[int, Field(gt=0)]
    items: Annotated[list[PurchaseItemIn], Field(min_length=1, max_length=MAX_ITEMS_PER_PURCHASE)]
    invoice_no: InvoiceNo | None = None
    total_amount: TotalAmount | None = None
    note: PurchaseNote | None = None

    @model_validator(mode="after")
    def _reject_duplicate_products(self) -> "PurchaseCreate":
        """Each product may appear only once; merge quantities client-side."""
        seen: set[int] = set()
        for item in self.items:
            if item.product_id in seen:
                raise ValueError(
                    f"product_id {item.product_id} appears more than once; "
                    "combine it into a single line."
                )
            seen.add(item.product_id)
        return self


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PurchaseItemOut(BaseModel):
    """One product line on a recorded purchase."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str | None = None
    unit: str | None = None
    quantity: Decimal
    unit_cost: Decimal
    line_total: Decimal

    @field_serializer("quantity")
    def _serialize_quantity(self, value: Decimal) -> str:
        return _quantity(value)

    @field_serializer("unit_cost", "line_total")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class PurchaseSummaryOut(BaseModel):
    """A purchase without its lines, used in lists."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name: str | None = None
    user_id: int | None
    invoice_no: str | None
    total_amount: Decimal
    item_count: int = 0
    note: str | None
    created_at: datetime

    @field_serializer("total_amount")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class PurchaseOut(PurchaseSummaryOut):
    """A full purchase with all of its lines."""

    items: list[PurchaseItemOut]


class PurchaseListOut(BaseModel):
    """List of purchases in the shared ``items`` / ``total`` shape."""

    items: list[PurchaseSummaryOut]
    total: int
