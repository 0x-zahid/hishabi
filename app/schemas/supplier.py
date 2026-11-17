"""Request and response schemas for suppliers.

Owner: Azaz (237). Field names follow the ``suppliers`` table in
``docs/schema.md`` section 3.8. Contact-field validation is shared with
``app/schemas/customer.py``.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_serializer, field_validator, model_validator

from app.schemas.auth import Email
from app.schemas.customer import Address, Note, PersonName, Phone, _blank_to_none

MONEY_PLACES = Decimal("0.01")

ContactPerson = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]

_OPTIONAL_TEXT = ("phone", "email", "contact_person", "address", "note")


class SupplierCreate(BaseModel):
    """Body for creating a supplier."""

    model_config = ConfigDict(extra="forbid")

    name: PersonName
    phone: Phone | None = None
    email: Email | None = None
    contact_person: ContactPerson | None = None
    address: Address | None = None
    note: Note | None = None

    _normalise_blanks = field_validator(*_OPTIONAL_TEXT, mode="before")(_blank_to_none)


class SupplierUpdate(BaseModel):
    """Partial update of a supplier. Only the fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: PersonName | None = None
    phone: Phone | None = None
    email: Email | None = None
    contact_person: ContactPerson | None = None
    address: Address | None = None
    note: Note | None = None
    is_active: bool | None = None

    _normalise_blanks = field_validator(*_OPTIONAL_TEXT, mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def _check_fields(self) -> "SupplierUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("name", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class SupplierOut(BaseModel):
    """Public representation of a supplier."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
    contact_person: str | None
    address: str | None
    note: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierDetailOut(SupplierOut):
    """Supplier profile with purchase statistics."""

    purchase_count: int = 0
    total_purchased: Decimal = Decimal("0")

    @field_serializer("total_purchased")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


class SupplierListOut(BaseModel):
    """List of suppliers in the shared ``items`` / ``total`` shape."""

    items: list[SupplierOut]
    total: int


class SupplierMessageResponse(BaseModel):
    """Simple confirmation message."""

    message: str
