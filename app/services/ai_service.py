"""AI Bangla entry: turning a Bangla sentence into a sale proposal.

Owner: Zahid. Module 3.

The flow of this service:

1. Check the daily limit for the user (R2). When it is reached the provider
   is never called and the request is refused with 429.
2. Send the sentence to the provider (``app/services/ai_provider.py``).
3. Parse the answer as JSON and validate it against ``AIExtractedData``
   (R5). The model's answer is never trusted.
4. Match the customer and the products against the database (R7 - R9).
5. Recompute the total from the item list on the server (R11).
6. Write one ``ai_request_logs`` row, whether or not the user goes on to
   confirm the proposal (R16).

Nothing is written to ``sales`` or ``payments`` here (R12). The sale is only
created when the user confirms, and then through the existing
``app/services/sale_service.py`` (R13).

"Today" means the server's local day, exactly like the daily reports
(``app/services/report_service.py`` uses ``date.today()`` and the database
timestamps are local too), so the limit resets at the same moment the daily
report does.
"""

import logging
import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_request_log import (
    COUNTED_STATUSES,
    STATUS_FAILED,
    STATUS_PROVIDER_ERROR,
    STATUS_QUOTA_EXCEEDED,
    STATUS_SUCCESS,
    AIRequestLog,
)
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.schemas.ai import (
    AIConfirmRequest,
    AIExtractedData,
    ProposalCustomer,
    ProposalItem,
    ProposalProduct,
    ProposalSuggestion,
    ProposalWarning,
    SaleProposal,
)
from app.schemas.sale import SaleCreate, SaleItemIn
from app.services import ai_provider, sale_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

ENTITY_TYPE = "ai_request_log"

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

# How many candidates are offered when a name did not match.
MAX_SUGGESTIONS = 5

# The safe message the client gets when the provider is unusable. It tells the
# user to fall back to the manual form (R4).
AI_UNAVAILABLE_MESSAGE = (
    "The AI service is unavailable right now. Please use the manual entry form."
)


def _error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    """Build the project's error shape with an optional extra flag."""
    detail: dict[str, Any] = {"code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def _normalise(name: str) -> str:
    """Fold a name for comparison: trimmed and lower case."""
    return name.strip().lower()


def _like_pattern(term: str) -> str:
    """Escape the wildcards of a LIKE pattern."""
    return term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# Daily limit
# ---------------------------------------------------------------------------


def _today_window() -> tuple[datetime, datetime]:
    """Return the half-open window [start, end) of the server's local day."""
    today = date.today()
    start = datetime.combine(today, time.min)
    return start, start + timedelta(days=1)


def count_requests_today(db: Session, user_id: int) -> int:
    """Count the user's AI requests of today that count against the limit.

    A request that the provider answered counts, even when the answer could
    not be used. A provider outage does not count: the user got nothing from
    it and must not be punished for the server being down.
    """
    start, end = _today_window()
    count = (
        db.query(AIRequestLog)
        .filter(
            AIRequestLog.user_id == user_id,
            AIRequestLog.status.in_(COUNTED_STATUSES),
            AIRequestLog.created_at >= start,
            AIRequestLog.created_at < end,
        )
        .count()
    )
    return int(count)


def get_usage(db: Session, user_id: int) -> dict[str, int]:
    """Return the user's usage of the daily limit."""
    limit = max(0, int(settings.AI_DAILY_LIMIT))
    used = count_requests_today(db, user_id)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _suggestions(db: Session, model: type, term: str) -> list[ProposalSuggestion]:
    """Return the closest rows for a name that did not match exactly.

    The full name is tried first; when that finds nothing, every word of the
    name is tried on its own, so "চাল ৫ কেজি" still offers "চাল".
    """
    needle = term.strip()
    if not needle:
        return []

    candidates: list[Any] = []
    seen: set[int] = set()

    terms = [needle]
    terms.extend(
        word for word in re.split(r"\s+", needle) if len(word) >= 2 and word != needle
    )

    for candidate_term in terms:
        pattern = f"%{_like_pattern(candidate_term)}%"
        rows = (
            db.query(model)
            .filter(model.name.ilike(pattern, escape="\\"))
            .order_by(func.length(model.name), model.id)
            .limit(MAX_SUGGESTIONS)
            .all()
        )
        for row in rows:
            if row.id not in seen:
                seen.add(row.id)
                candidates.append(row)
        if len(candidates) >= MAX_SUGGESTIONS:
            break

    return [ProposalSuggestion(id=row.id, name=row.name) for row in candidates[:MAX_SUGGESTIONS]]


def _match_customer(
    db: Session, name: str
) -> tuple[Customer | None, list[ProposalSuggestion], str | None]:
    """Match a customer name.

    A match ignores case and surrounding whitespace. An inactive customer
    still matches but carries a warning, so the user can see it and decide
    (R9). No match is not an error (R7).
    """
    needle = _normalise(name)
    customer = (
        db.query(Customer)
        .filter(func.lower(func.trim(Customer.name)) == needle)
        .first()
    )
    if customer is None:
        return None, _suggestions(db, Customer, name), None

    if not customer.is_active:
        warning = f"Customer '{customer.name}' is inactive."
        return customer, [], warning
    return customer, [], None


def _match_product(
    db: Session, name: str
) -> tuple[Product | None, list[ProposalSuggestion], str | None]:
    """Match a product name the same way a customer name is matched (R8, R9)."""
    needle = _normalise(name)
    product = (
        db.query(Product)
        .filter(func.lower(func.trim(Product.name)) == needle)
        .first()
    )
    if product is None:
        return None, _suggestions(db, Product, name), None

    if not product.is_active:
        warning = f"Product '{product.name}' is inactive."
        return product, [], warning
    return product, [], None


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


def compute_total(items: list[dict[str, Any]]) -> Decimal:
    """Recompute the total from the item list.

    The model's own ``total_amount`` is never used (R11).
    """
    total = Decimal("0")
    for item in items:
        quantity = Decimal(str(item.get("quantity", 0)))
        unit_price = Decimal(str(item.get("unit_price", 0)))
        total += quantity * unit_price
    return _money(total)


def build_proposal(
    db: Session, extracted: AIExtractedData
) -> tuple[SaleProposal, list[ProposalWarning]]:
    """Turn the validated extraction into an editable, database-matched proposal."""
    warnings: list[ProposalWarning] = []
    proposal_flags: list[str] = []

    # --- Customer --------------------------------------------------------
    customer_field = ProposalCustomer(id=None, name=None, matched=False, warning=None)
    raw_customer_name = (extracted.customer_name or "").strip()
    if raw_customer_name:
        customer, suggestions, warning = _match_customer(db, raw_customer_name)
        if customer is not None:
            customer_field = ProposalCustomer(
                id=customer.id,
                name=customer.name,
                matched=True,
                warning=warning,
            )
            if warning:
                warnings.append(
                    ProposalWarning(field="customer", message=warning, suggestions=[])
                )
        else:
            customer_field = ProposalCustomer(
                id=None,
                name=raw_customer_name,
                matched=False,
                warning=f"No customer matched '{raw_customer_name}'.",
            )
            warnings.append(
                ProposalWarning(
                    field="customer",
                    message=f"No customer matched '{raw_customer_name}'.",
                    suggestions=suggestions,
                )
            )
            proposal_flags.append("customer_not_matched")

    # --- Items -----------------------------------------------------------
    proposal_items: list[ProposalItem] = []
    for index, item in enumerate(extracted.items):
        flags: list[str] = []
        product, suggestions, warning = _match_product(db, item.product_name)

        if item.quantity <= 0:
            flags.append("quantity must be greater than zero")
        if item.unit_price < 0:
            flags.append("unit_price cannot be negative")

        if product is None:
            product_field = ProposalProduct(
                id=None, name=item.product_name.strip(), matched=False
            )
            flags.append("product not matched")
            warnings.append(
                ProposalWarning(
                    field=f"items[{index}].product",
                    message=f"No product matched '{item.product_name.strip()}'.",
                    suggestions=suggestions,
                )
            )
        else:
            product_field = ProposalProduct(
                id=product.id, name=product.name, matched=True
            )
            if warning:
                flags.append("product is inactive")
                warnings.append(
                    ProposalWarning(
                        field=f"items[{index}].product",
                        message=warning,
                        suggestions=[],
                    )
                )

        proposal_items.append(
            ProposalItem(
                product=product_field,
                quantity=_quantity(item.quantity),
                unit_price=_money(item.unit_price),
                flags=flags,
            )
        )

    if not proposal_items:
        proposal_flags.append("no_items")

    # --- Money ------------------------------------------------------------
    # The total always comes from the item list (R11).
    total = compute_total(
        [
            {"quantity": item.quantity, "unit_price": item.unit_price}
            for item in extracted.items
        ]
    )

    if extracted.total_amount is not None and _money(extracted.total_amount) != total:
        warnings.append(
            ProposalWarning(
                field="total_amount",
                message=(
                    f"The AI reported a total of {_money(extracted.total_amount)}; "
                    f"the server computed {total} from the items and used that."
                ),
                suggestions=[],
            )
        )

    payment_type = extracted.payment_type
    if extracted.paid_amount is None:
        # A cash sale with no stated amount is paid in full; a credit sale
        # with no stated amount is unpaid.
        paid = total if payment_type == "cash" else _money(Decimal("0"))
    else:
        paid = _money(extracted.paid_amount)

    if paid < 0:
        proposal_flags.append("paid_amount cannot be negative")
    if payment_type == "cash" and paid != total:
        proposal_flags.append("paid_amount must equal the total for a cash sale")
    if payment_type == "credit":
        if customer_field.id is None:
            proposal_flags.append("customer_required_for_credit")
        if paid > total:
            proposal_flags.append("paid_amount cannot be larger than the total")

    proposal = SaleProposal(
        customer=customer_field,
        items=proposal_items,
        payment_type=payment_type,
        paid_amount=paid,
        total_amount=total,
        flags=proposal_flags,
    )
    return proposal, warnings


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def _log_request(
    db: Session,
    *,
    user_id: int,
    input_text: str,
    status_value: str,
    ai_response: str | None = None,
    extracted_data: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> AIRequestLog:
    """Write one ``ai_request_logs`` row."""
    row = AIRequestLog(
        user_id=user_id,
        input_text=input_text,
        ai_response=ai_response,
        extracted_data=extracted_data,
        status=status_value,
        error_message=error_message,
        confirmed=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def parse_sale_sentence(
    db: Session, user_id: int, text: str, ip_address: str | None = None
) -> tuple[AIRequestLog, SaleProposal, list[ProposalWarning], int]:
    """Parse a Bangla sentence into a proposal.

    Returns the log row, the proposal, the warnings and how many requests the
    user has left today.
    """
    # --- 1. The daily limit (R2) ----------------------------------------
    usage = get_usage(db, user_id)
    if usage["used"] >= usage["limit"]:
        # The attempt is recorded, so a user cannot probe the limit for free,
        # but it does not count against the limit itself.
        _log_request(
            db,
            user_id=user_id,
            input_text=text,
            status_value=STATUS_QUOTA_EXCEEDED,
            error_message="Daily AI request limit reached.",
        )
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "AI_DAILY_LIMIT_REACHED",
            f"You have used all {usage['limit']} AI requests for today.",
            remaining_requests_today=0,
        )

    # --- 2. The provider ------------------------------------------------
    try:
        raw_response = ai_provider.call_model(text)
    except ai_provider.AIProviderError as exc:
        # The raw provider text stays in the log, never in the answer (R18).
        _log_request(
            db,
            user_id=user_id,
            input_text=text,
            status_value=STATUS_PROVIDER_ERROR,
            error_message=exc.detail or exc.message,
        )
        logger.warning("AI provider unavailable: %s", exc.detail or exc.message)
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_SERVICE_UNAVAILABLE",
            AI_UNAVAILABLE_MESSAGE,
            use_manual_entry=True,
        ) from exc

    # --- 3. Parse and validate (R5) -------------------------------------
    try:
        parsed = ai_provider.parse_json_response(raw_response)
    except ai_provider.AIProviderError as exc:
        _log_request(
            db,
            user_id=user_id,
            input_text=text,
            status_value=STATUS_FAILED,
            ai_response=raw_response,
            error_message=exc.detail or exc.message,
        )
        logger.warning("AI response was not readable: %s", exc.detail or exc.message)
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_SERVICE_UNAVAILABLE",
            AI_UNAVAILABLE_MESSAGE,
            use_manual_entry=True,
        ) from exc

    try:
        extracted = AIExtractedData.model_validate(parsed)
    except ValidationError as exc:
        _log_request(
            db,
            user_id=user_id,
            input_text=text,
            status_value=STATUS_FAILED,
            ai_response=raw_response,
            error_message=str(exc),
        )
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_AI_RESPONSE",
            f"The AI response did not match the expected shape: {_first_field_error(exc)}",
        ) from exc

    # --- 4 and 5. Match and total --------------------------------------
    proposal, warnings = build_proposal(db, extracted)

    # --- 6. Record the request (R16) -----------------------------------
    row = _log_request(
        db,
        user_id=user_id,
        input_text=text,
        status_value=STATUS_SUCCESS,
        ai_response=raw_response,
        extracted_data={
            "proposal": proposal.model_dump(mode="json"),
            "warnings": [warning.model_dump(mode="json") for warning in warnings],
        },
    )

    remaining = max(0, usage["limit"] - (usage["used"] + 1))
    return row, proposal, warnings, remaining


def _first_field_error(exc: ValidationError) -> str:
    """Return the first invalid field of a validation error, named for the user."""
    errors = exc.errors()
    if not errors:
        return "unknown field"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = first.get("msg", "invalid value")
    return f"{location}: {message}" if location else str(message)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_request(db: Session, user_id: int, request_id: int) -> AIRequestLog:
    """Return one of the user's own requests, or raise 404.

    Another user's request is reported as missing, so the answer never
    reveals that it exists.
    """
    row = (
        db.query(AIRequestLog)
        .filter(AIRequestLog.id == request_id, AIRequestLog.user_id == user_id)
        .first()
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "AI_REQUEST_NOT_FOUND",
            "AI request not found.",
        )
    return row


def stored_proposal(row: AIRequestLog) -> tuple[SaleProposal | None, list[ProposalWarning]]:
    """Read the proposal and the warnings back out of a stored row."""
    if not row.extracted_data:
        return None, []
    raw_proposal = row.extracted_data.get("proposal")
    proposal = (
        SaleProposal.model_validate(raw_proposal) if raw_proposal is not None else None
    )
    raw_warnings = row.extracted_data.get("warnings") or []
    warnings = [ProposalWarning.model_validate(item) for item in raw_warnings]
    return proposal, warnings


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------


def _proposal_to_sale_body(body: AIConfirmRequest) -> SaleCreate:
    """Re-validate the edited proposal and turn it into a sale body.

    The total is recomputed here, so the client can never talk the sale
    service into accepting a wrong total (R11).
    """
    if not body.items:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_SALE_ITEMS",
            "items: a sale must contain at least one item.",
        )

    if body.payment_type not in ("cash", "credit"):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_PAYMENT_TYPE",
            "payment_type: must be 'cash' or 'credit'.",
        )

    sale_items: list[SaleItemIn] = []
    for index, item in enumerate(body.items):
        if item.product.id is None:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "PRODUCT_NOT_SELECTED",
                f"items[{index}].product: choose a product before confirming.",
            )
        if item.quantity <= 0:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_QUANTITY",
                f"items[{index}].quantity: must be greater than zero.",
            )
        if item.unit_price < 0:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_UNIT_PRICE",
                f"items[{index}].unit_price: cannot be negative.",
            )
        sale_items.append(
            SaleItemIn(
                product_id=item.product.id,
                quantity=_quantity(item.quantity),
                unit_price=_money(item.unit_price),
            )
        )

    customer_id = body.customer.id if body.customer is not None else None
    if body.payment_type == "credit" and customer_id is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CUSTOMER_REQUIRED",
            "customer: a credit sale must name the customer it is sold to.",
        )

    total = compute_total(
        [
            {"quantity": item.quantity, "unit_price": item.unit_price}
            for item in body.items
        ]
    )

    if body.paid_amount is None:
        paid = total if body.payment_type == "cash" else _money(Decimal("0"))
    else:
        paid = _money(body.paid_amount)

    return SaleCreate(
        customer_id=customer_id,
        payment_type=body.payment_type,
        items=sale_items,
        paid_amount=paid,
        note=body.note,
        total_amount=total,
    )


def confirm_request(
    db: Session,
    user_id: int,
    request_id: int,
    body: AIConfirmRequest,
    ip_address: str | None = None,
) -> Sale:
    """Create the sale behind a confirmed proposal.

    The sale is created through the existing sale service, so the stock
    check, the ledger and the audit row all behave exactly as they do for a
    sale recorded by hand (R13). The service's own errors are left to reach
    the user unchanged.
    """
    row = (
        db.query(AIRequestLog)
        .filter(AIRequestLog.id == request_id, AIRequestLog.user_id == user_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "AI_REQUEST_NOT_FOUND",
            "AI request not found.",
        )
    if row.confirmed:
        raise _error(
            status.HTTP_409_CONFLICT,
            "AI_REQUEST_ALREADY_CONFIRMED",
            "This proposal has already been confirmed.",
        )

    sale_body = _proposal_to_sale_body(body)

    # The row is marked before the sale is created, so both land in the same
    # transaction. If the sale fails, the rollback takes the mark with it and
    # the proposal can be tried again.
    row.confirmed = True
    row.extracted_data = {
        "proposal": _confirmed_proposal(body, sale_body).model_dump(mode="json"),
        "warnings": (row.extracted_data or {}).get("warnings", []),
    }
    db.flush()

    log_action(
        db,
        user_id=user_id,
        action="confirm",
        entity_type=ENTITY_TYPE,
        entity_id=row.id,
        old_value=None,
        new_value={
            "payment_type": sale_body.payment_type,
            "total_amount": str(sale_body.total_amount),
            "paid_amount": str(sale_body.paid_amount),
            "items": [
                {
                    "product_id": item.product_id,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                }
                for item in sale_body.items
            ],
        },
        ip_address=ip_address,
    )

    # The sale service commits the whole transaction, including the mark and
    # the audit row above.
    sale = sale_service.record_sale(db, sale_body, user_id, ip_address)
    return sale


def _confirmed_proposal(body: AIConfirmRequest, sale_body: SaleCreate) -> SaleProposal:
    """Build the stored proposal for a confirmed request."""
    return SaleProposal(
        customer=ProposalCustomer(
            id=sale_body.customer_id,
            name=body.customer.name if body.customer is not None else None,
            matched=sale_body.customer_id is not None,
            warning=None,
        ),
        items=[
            ProposalItem(
                product=ProposalProduct(id=item.product_id, name=None, matched=True),
                quantity=item.quantity,
                unit_price=item.unit_price,
                flags=[],
            )
            for item in sale_body.items
        ],
        payment_type=sale_body.payment_type,
        paid_amount=sale_body.paid_amount,
        total_amount=sale_body.total_amount,
        flags=[],
    )


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


def reject_request(db: Session, user_id: int, request_id: int) -> str:
    """Discard a proposal. Nothing is saved.

    A proposal that has already been confirmed cannot be thrown away: the
    sale behind it exists, so it is refused with 409.
    """
    row = get_request(db, user_id, request_id)
    if row.confirmed:
        raise _error(
            status.HTTP_409_CONFLICT,
            "AI_REQUEST_ALREADY_CONFIRMED",
            "This proposal has already been confirmed.",
        )
    return f"AI request {row.id} was discarded. Nothing was saved."
