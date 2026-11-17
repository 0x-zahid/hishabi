"""Request and response schemas for customers.

Owner: Azaz (237). Field names follow the ``customers`` table in
``docs/schema.md`` section 3.7.

The contact-field types defined here (``PersonName``, ``Phone``, ``Address``,
``Note``) are reused by ``app/schemas/supplier.py`` so both resources validate
contact details the same way.

Money in the history summary is ``Decimal`` serialised as a JSON string, the
same as ``app/schemas/product.py``.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from app.schemas.auth import Email

MONEY_PLACES = Decimal("0.01")

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
# Digits with an optional leading "+": covers 01XXXXXXXXX and +8801XXXXXXXXX.
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=6, max_length=20, pattern=r"^\+?[0-9]{6,19}$"),
]
Address = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


def _blank_to_none(value: Any) -> Any:
    """Treat an empty or whitespace-only optional string as "not provided".

    ``phone`` is UNIQUE in the database. Storing ``""`` would let only one
    customer have no phone, so blanks are normalised to ``None``.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


class CustomerCreate(BaseModel):
    """Body for creating a customer."""

    model_config = ConfigDict(extra="forbid")

    name: PersonName
    phone: Phone | None = None
    email: Email | None = None
    address: Address | None = None
    note: Note | None = None

    _normalise_blanks = field_validator("phone", "email", "address", "note", mode="before")(
        _blank_to_none
    )


class CustomerUpdate(BaseModel):
    """Partial update of a customer. Only the fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: PersonName | None = None
    phone: Phone | None = None
    email: Email | None = None
    address: Address | None = None
    note: Note | None = None
    is_active: bool | None = None

    _normalise_blanks = field_validator("phone", "email", "address", "note", mode="before")(
        _blank_to_none
    )

    @model_validator(mode="after")
    def _check_fields(self) -> "CustomerUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("name", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class CustomerOut(BaseModel):
    """Public representation of a customer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
    address: str | None
    note: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerListOut(BaseModel):
    """List of customers in the shared ``items`` / ``total`` shape."""

    items: list[CustomerOut]
    total: int


class CustomerMessageResponse(BaseModel):
    """Simple confirmation message."""

    message: str


# ---------------------------------------------------------------------------
# Customer history
# ---------------------------------------------------------------------------


class CustomerActivityOut(BaseModel):
    """One audit-log entry about this customer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str | None
    user_id: int | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime


class CustomerSummaryOut(BaseModel):
    """Money summary for a customer.

    Sales, payments and dues belong to Zahid's module. Until his tables exist
    these are zero; they will be filled from his read-only helper afterwards.
    """

    total_sales: Decimal = Decimal("0")
    total_paid: Decimal = Decimal("0")
    current_due: Decimal = Decimal("0")

    @field_serializer("total_sales", "total_paid", "current_due")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


class CustomerHistoryOut(BaseModel):
    """Customer profile with purchases, dues, payments and recent activity.

    ``sales`` and ``payments`` are lists of plain objects whose shape is owned
    by Zahid's sales/payments module; this schema does not constrain them.
    """

    customer: CustomerOut
    summary: CustomerSummaryOut = Field(default_factory=CustomerSummaryOut)
    sales: list[dict[str, Any]] = Field(default_factory=list)
    payments: list[dict[str, Any]] = Field(default_factory=list)
    recent_activity: list[CustomerActivityOut] = Field(default_factory=list)
