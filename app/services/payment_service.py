"""Payment recording: one transaction that stores a payment and its audit row.

Owner: Zahid. Module 2 (sales and customer dues).

Recording a payment is a single database transaction:

1. Validate that the customer exists and is active.
2. Validate that the referenced sale, if any, exists and belongs to that
   customer.
3. Compute the customer's outstanding due with
   ``app/services/dues_service.py`` and reject a payment larger than it.
4. Insert the ``payments`` row.
5. Write one audit row through ``audit_service.log_action``.
6. Commit once.

If any step fails, everything is rolled back.

The due itself is never written anywhere: it stays a computed value, so a
payment can never leave the customer and the ledger disagreeing (R16).

Payments are immutable (R19): there is no update and no delete.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.payment import Payment
from app.models.sale import Sale
from app.schemas.payment import PaymentCreate
from app.services import dues_service
from app.services.audit_service import log_action

ENTITY_TYPE = "payment"
MONEY_PLACES = Decimal("0.01")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def record_payment(
    db: Session, body: PaymentCreate, user_id: int, ip_address: str | None = None
) -> Payment:
    """Record a payment against a customer's due, all in one transaction."""
    try:
        payment = _record_payment(db, body, user_id, ip_address)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return payment


def _record_payment(
    db: Session, body: PaymentCreate, user_id: int, ip_address: str | None
) -> Payment:
    # --- 1. Amount (R21) ------------------------------------------------
    amount = _money(body.amount)
    if amount <= 0:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_PAYMENT_AMOUNT",
            "The payment amount must be greater than zero.",
        )

    # --- 2. Customer (R18, R23) -----------------------------------------
    # The customer row is locked so that two payments taken at the same
    # moment cannot both read the same outstanding due and both pass the
    # overpayment check. Without the lock a customer could be paid twice the
    # amount they owe by two concurrent requests (R17).
    customer = (
        db.query(Customer).filter(Customer.id == body.customer_id).with_for_update().first()
    )
    if not customer:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "CUSTOMER_NOT_FOUND",
            "Customer not found.",
        )
    if not customer.is_active:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CUSTOMER_INACTIVE",
            f"Customer '{customer.name}' is inactive and cannot make a payment.",
        )

    # --- 3. The linked sale ----------------------------------------------
    sale: Sale | None = None
    if body.sale_id is not None:
        sale = db.query(Sale).filter(Sale.id == body.sale_id).first()
        if not sale:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "SALE_NOT_FOUND",
                "Sale not found.",
            )
        if sale.customer_id != customer.id:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "SALE_CUSTOMER_MISMATCH",
                f"Sale #{sale.id} does not belong to customer '{customer.name}'.",
            )

    # --- 4. Overpayment check (R17) -------------------------------------
    current_due = dues_service.get_customer_due(db, customer.id)
    if amount > current_due:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "OVERPAYMENT_NOT_ALLOWED",
            f"The payment {amount} is larger than the outstanding due {current_due}.",
        )

    # --- 5. Write the payment -------------------------------------------
    payment = Payment(
        customer_id=customer.id,
        user_id=user_id,
        sale_id=sale.id if sale else None,
        amount=amount,
        payment_method=body.payment_method,
        note=body.note,
    )
    db.add(payment)
    db.flush()

    # --- 6. Audit (R15) --------------------------------------------------
    log_action(
        db,
        user_id=user_id,
        action="create",
        entity_type=ENTITY_TYPE,
        entity_id=payment.id,
        old_value=None,
        new_value={
            "customer_id": customer.id,
            "amount": str(amount),
            "payment_method": payment.payment_method,
            "sale_id": payment.sale_id,
        },
        ip_address=ip_address,
    )
    return payment


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_payment(db: Session, payment_id: int) -> Payment:
    """Return the payment or raise 404."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise _error(status.HTTP_404_NOT_FOUND, "PAYMENT_NOT_FOUND", "Payment not found.")
    return payment


def to_summary(payment: Payment) -> dict[str, Any]:
    """Flatten a payment for the response schemas."""
    return {
        "id": payment.id,
        "customer_id": payment.customer_id,
        "customer_name": payment.customer.name if payment.customer else None,
        "user_id": payment.user_id,
        "sale_id": payment.sale_id,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "note": payment.note,
        "created_at": payment.created_at,
    }


def to_summary_dict(
    history_item: dict[str, Any], payment: Payment | None = None
) -> dict[str, Any]:
    """Flatten one entry of the shared dues-service payment history.

    ``dues_service.get_customer_payment_history()`` returns the plain dict
    shape of the shared contract. This adds the customer name and the staff
    id that the response schema carries, so the endpoint and the service can
    never disagree about the history.
    """
    return {
        "id": history_item["id"],
        "customer_id": history_item["customer_id"],
        "customer_name": (
            payment.customer.name if payment is not None and payment.customer else None
        ),
        "user_id": payment.user_id if payment is not None else None,
        "sale_id": history_item["sale_id"],
        "amount": history_item["amount"],
        "payment_method": history_item["payment_method"],
        "note": history_item["note"],
        "created_at": history_item["created_at"],
    }


def history_page(
    db: Session, customer_id: int, skip: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Return one page of a customer's payment history and the total count.

    The history itself comes from the shared ``dues_service``, so the endpoint
    and ``dues_service.get_customer_payment_history()`` are the same thing.
    """
    history = dues_service.get_customer_payment_history(db, customer_id)
    total = len(history)
    page_items = history[skip : skip + limit]
    if not page_items:
        return [], total

    rows = {
        payment.id: payment
        for payment in db.query(Payment)
        .filter(Payment.id.in_([item["id"] for item in page_items]))
        .all()
    }
    items = [to_summary_dict(item, rows.get(item["id"])) for item in page_items]
    return items, total
