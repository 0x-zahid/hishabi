"""Request and response schemas for stock movements.

Owner: Zahid. Field names follow the ``stock_movements`` table in
``docs/schema.md`` section 3.5.

Quantity is ``NUMERIC(12,3)`` and is handled as ``Decimal`` only, never
``float``. It is serialised as a JSON string, matching the money handling in
``app/schemas/product.py``.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

QUANTITY_PLACES = Decimal("0.001")

# NUMERIC(12,3): at most 12 digits in total, 3 of them after the decimal point.
Quantity = Annotated[Decimal, Field(max_digits=12, decimal_places=3)]

MovementType = Literal["purchase", "sale", "return", "adjustment"]

# Movements that increase stock. A return brings goods back from a customer.
INBOUND_TYPES = {"purchase", "return"}
# Movements that decrease stock.
OUTBOUND_TYPES = {"sale"}


class StockMovementCreate(BaseModel):
    """Body for recording a stock movement.

    ``quantity`` is the absolute size of the movement for ``purchase``,
    ``sale`` and ``return``, and must be positive. For ``adjustment`` it is
    signed: a negative value reduces stock and a positive value increases it.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: Annotated[int, Field(gt=0)]
    movement_type: MovementType
    quantity: Quantity
    note: Annotated[str, Field(max_length=255)] | None = None

    @model_validator(mode="after")
    def _check_quantity_sign(self) -> "StockMovementCreate":
        """Reject a negative quantity except on an adjustment.

        An adjustment is the one movement whose direction is carried by the
        sign of the quantity, so it is the only one allowed to be negative.
        """
        if self.movement_type != "adjustment" and self.quantity < 0:
            raise ValueError(
                "quantity must be positive for purchase, sale and return; "
                "only an adjustment may be negative."
            )
        if self.movement_type == "adjustment" and self.quantity == 0:
            raise ValueError("quantity must not be zero for an adjustment.")
        return self


class StockMovementOut(BaseModel):
    """Public representation of a stock movement."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None
    user_id: int | None
    movement_type: str | None
    quantity: Decimal
    balance_after: Decimal | None
    reference_type: str | None
    reference_id: int | None
    note: str | None
    created_at: datetime

    @field_serializer("quantity", "balance_after")
    def _serialize_quantity(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


class StockMovementListOut(BaseModel):
    """List of stock movements in the shared ``items`` / ``total`` shape."""

    items: list[StockMovementOut]
    total: int


class LowStockProductOut(BaseModel):
    """A product whose stock has reached its low-stock threshold."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    name: str
    unit: str
    current_stock: Decimal
    low_stock_threshold: Decimal

    @field_serializer("current_stock", "low_stock_threshold")
    def _serialize_quantity(self, value: Decimal) -> str:
        return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


class LowStockListOut(BaseModel):
    """List of low-stock products in the shared ``items`` / ``total`` shape."""

    items: list[LowStockProductOut]
    total: int


class StockMessageResponse(BaseModel):
    """Response returned when a stock movement is recorded."""

    message: str = "Stock movement recorded successfully."
