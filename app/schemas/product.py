"""Request and response schemas for products.

Owner: Azaz (237). Field names follow the ``products`` table in
``docs/schema.md`` section 3.4.

Money is ``NUMERIC(12,2)`` and quantity is ``NUMERIC(12,3)``. Both are handled
as ``Decimal`` only, never ``float``, and are serialised as JSON strings
(schema.md section 7.2) rounded with ``ROUND_HALF_UP``.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer, model_validator

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

# NUMERIC(12,2): at most 12 digits in total, 2 of them after the decimal point.
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
SalePrice = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
# NUMERIC(12,3): at most 12 digits in total, 3 of them after the decimal point.
Quantity = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]

ProductName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
CategoryId = Annotated[int, Field(gt=0)]


class ProductCreate(BaseModel):
    """Body for creating a product.

    ``current_stock`` is the opening stock only. After creation, stock changes
    go through stock movements (Zahid's module), so it is not editable later.
    """

    model_config = ConfigDict(extra="forbid")

    category_id: CategoryId | None = None
    name: ProductName
    unit: Unit
    purchase_price: Money = Decimal("0")
    sale_price: SalePrice
    current_stock: Quantity = Decimal("0")
    low_stock_threshold: Quantity = Decimal("0")


# Columns that are NOT NULL in the database: an explicit null in an update is invalid.
_NON_NULLABLE_UPDATE_FIELDS = (
    "name",
    "unit",
    "purchase_price",
    "sale_price",
    "low_stock_threshold",
    "is_active",
)


class ProductUpdate(BaseModel):
    """Partial update of a product. Only the fields that are sent are changed.

    ``current_stock`` is deliberately absent and is rejected with a 422.
    """

    model_config = ConfigDict(extra="forbid")

    category_id: CategoryId | None = None
    name: ProductName | None = None
    unit: Unit | None = None
    purchase_price: Money | None = None
    sale_price: SalePrice | None = None
    low_stock_threshold: Quantity | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _reject_null_for_required_columns(self) -> "ProductUpdate":
        for field in _NON_NULLABLE_UPDATE_FIELDS:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ProductOut(BaseModel):
    """Public representation of a product."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    name: str
    unit: str
    purchase_price: Decimal
    sale_price: Decimal
    current_stock: Decimal
    low_stock_threshold: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("purchase_price", "sale_price")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))

    @field_serializer("current_stock", "low_stock_threshold")
    def _serialize_quantity(self, value: Decimal) -> str:
        return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


class ProductListOut(BaseModel):
    """List of products in the shared ``items`` / ``total`` shape."""

    items: list[ProductOut]
    total: int


class ProductMessageResponse(BaseModel):
    """Response returned upon product deletion."""

    message: str = "Product deleted successfully."
