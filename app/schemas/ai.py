"""Request and response schemas for the AI Bangla entry feature.

Owner: Zahid. Module 3.

Two groups of schemas live here:

* ``AIExtractedData`` is the fixed shape the model must answer with. It is
  the schema the provider's JSON is validated against, so the model's answer
  is never trusted (R5).
* the ``Proposal*`` schemas are the server's own, validated view of a sale
  that the user may still edit before confirming (R12).

Money and quantity are ``Decimal`` only, never ``float``, and are serialised
as JSON strings rounded half-up, exactly like every other schema in the
project (``docs/schema.md`` section 7.2).
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

# A sale never carries more lines than this, so a proposal may not either.
MAX_ITEMS_PER_PROPOSAL = 100

PaymentType = Literal["cash", "credit"]

AiText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


def _quantity(value: Decimal) -> str:
    return str(value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# The AI extraction: the fixed shape (R6)
# ---------------------------------------------------------------------------


class AIExtractedItem(BaseModel):
    """One product line as the model described it.

    The values are deliberately unconstrained here: a zero quantity or a
    negative price is a mistake the user can correct in the review form, so it
    is flagged (R10) instead of throwing the whole proposal away.
    """

    model_config = ConfigDict(extra="ignore")

    product_name: str
    quantity: Decimal
    unit_price: Decimal


class AIExtractedData(BaseModel):
    """The fixed JSON shape the model is asked to answer with.

    Extra keys are ignored so a chatty model does not cost the user the
    proposal, but every key below is required or has an explicit default.
    """

    model_config = ConfigDict(extra="ignore")

    customer_name: str | None = None
    items: list[AIExtractedItem] = Field(max_length=MAX_ITEMS_PER_PROPOSAL)
    payment_type: PaymentType
    paid_amount: Decimal | None = None
    total_amount: Decimal


# ---------------------------------------------------------------------------
# The proposal: what the user reviews and edits
# ---------------------------------------------------------------------------


class ProposalSuggestion(BaseModel):
    """A database row the user may pick instead of the unmatched name."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str


class ProposalCustomer(BaseModel):
    """The customer of the proposal."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str | None = None
    matched: bool = False
    # Set when the customer is inactive (R9) or when nothing matched (R7).
    warning: str | None = None


class ProposalProduct(BaseModel):
    """The product of one line of the proposal."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str | None = None
    matched: bool = False


class ProposalItem(BaseModel):
    """One editable line of the proposal."""

    model_config = ConfigDict(extra="forbid")

    product: ProposalProduct
    quantity: Decimal
    unit_price: Decimal
    # Problems the user must fix before confirming (R10, R9).
    flags: list[str] = Field(default_factory=list)

    @field_serializer("quantity")
    def _serialize_quantity(self, value: Decimal) -> str:
        return _quantity(value)

    @field_serializer("unit_price")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class SaleProposal(BaseModel):
    """A sale proposal: the whole record the user may edit before confirming."""

    model_config = ConfigDict(extra="forbid")

    customer: ProposalCustomer
    items: list[ProposalItem]
    payment_type: str
    paid_amount: Decimal
    # Always the server-computed total, never the model's number (R11).
    total_amount: Decimal
    # Proposal-level problems the user must fix before confirming.
    flags: list[str] = Field(default_factory=list)

    @field_serializer("paid_amount", "total_amount")
    def _serialize_money(self, value: Decimal) -> str:
        return _money(value)


class ProposalWarning(BaseModel):
    """A note about one field of the proposal, with candidates to pick."""

    model_config = ConfigDict(extra="forbid")

    field: str
    message: str
    suggestions: list[ProposalSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class AIParseRequest(BaseModel):
    """Body of ``POST /api/v1/ai/parse``."""

    model_config = ConfigDict(extra="forbid")

    text: AiText


class AIParseResponse(BaseModel):
    """The answer of ``POST /api/v1/ai/parse``."""

    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: str
    proposal: SaleProposal
    warnings: list[ProposalWarning] = Field(default_factory=list)
    remaining_requests_today: int


class AIUsageOut(BaseModel):
    """The answer of ``GET /api/v1/ai/requests/today``."""

    model_config = ConfigDict(extra="forbid")

    used: int
    limit: int
    remaining: int


class AIRequestOut(BaseModel):
    """A stored AI request and the proposal it produced."""

    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: str
    input_text: str
    proposal: SaleProposal | None = None
    warnings: list[ProposalWarning] = Field(default_factory=list)
    confirmed: bool
    created_at: datetime


class AIRequestMessageOut(BaseModel):
    """A short confirmation, used by the reject endpoint."""

    model_config = ConfigDict(extra="forbid")

    message: str


# ---------------------------------------------------------------------------
# The edited proposal the user sends back to confirm
# ---------------------------------------------------------------------------


class ConfirmCustomerIn(BaseModel):
    """The customer the user chose in the review form.

    ``extra="ignore"`` lets the client send back the whole proposal object it
    holds, including the read-only ``matched`` and ``warning`` fields.
    """

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class ConfirmProductIn(BaseModel):
    """The product the user chose for one line."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class ConfirmItemIn(BaseModel):
    """One edited line of the proposal."""

    model_config = ConfigDict(extra="ignore")

    product: ConfirmProductIn
    quantity: Decimal
    unit_price: Decimal


class AIConfirmRequest(BaseModel):
    """Body of ``POST /api/v1/ai/requests/{request_id}/confirm``.

    This is the proposal as the user changed it in the review form. It is
    re-validated on the server before the sale is created (R13).
    """

    model_config = ConfigDict(extra="ignore")

    customer: ConfirmCustomerIn | None = None
    items: list[ConfirmItemIn]
    payment_type: PaymentType
    paid_amount: Decimal | None = None
    total_amount: Decimal | None = None
    note: Note | None = None
