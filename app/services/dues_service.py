"""Customer due calculations.

Owner: Zahid. Module 2 (sales and customer dues).

This module is the **single source of truth** for a customer's outstanding
due. The due is never stored on any table: it is computed from the credit
sales and the payments every time it is needed (R16). That is why the
``customers`` table has no ``due`` column — one computation, one answer.

Every function here is a pure query: no writes, no ``commit``, no
``HTTPException``. The router layer converts the returned dicts into response
schemas and raises the HTTP errors, so this service can be reused from
anywhere — including from ``app/services/report_service.py`` (Azaz, 237),
whose ``get_due_report()`` currently hardcodes every due to ``0.00``.

Money is ``Decimal`` throughout, never ``float``, and every returned amount is
rounded half-up to two decimal places exactly like the ``_money`` helper in
``app/services/report_service.py``.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.payment import Payment
from app.models.sale import Sale

MONEY_PLACES = Decimal("0.01")


def _money(value: Decimal | int | float | None) -> Decimal:
    """Return ``value`` as a two-decimal ``Decimal``, rounded half-up."""
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Core queries
# ---------------------------------------------------------------------------


def _credit_sales_totals(db: Session, customer_id: int) -> dict[str, Any]:
    """Return the credit-sale totals of one customer.

    ``total_credit_sales`` is the gross value sold on credit,
    ``total_paid_at_counter`` is the part of it that was paid at the time of
    the sale, and ``due_at_counter`` is what was actually put on account
    (``SUM(sales.due_amount)``).
    """
    row = (
        db.query(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.paid_amount), 0),
            func.coalesce(func.sum(Sale.due_amount), 0),
            func.count(Sale.id),
        )
        .filter(Sale.customer_id == customer_id, Sale.payment_type == "credit")
        .one()
    )
    total_credit_sales, total_paid_at_counter, due_at_counter, sale_count = row
    return {
        "total_credit_sales": _money(total_credit_sales),
        "total_paid_at_counter": _money(total_paid_at_counter),
        "due_at_counter": _money(due_at_counter),
        "sale_count": int(sale_count),
    }


def _payment_totals(db: Session, customer_id: int) -> dict[str, Any]:
    """Return the payment totals of one customer."""
    row = (
        db.query(
            func.coalesce(func.sum(Payment.amount), 0),
            func.count(Payment.id),
        )
        .filter(Payment.customer_id == customer_id)
        .one()
    )
    total_paid, payment_count = row
    return {"total_paid": _money(total_paid), "payment_count": int(payment_count)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_customer_due(db: Session, customer_id: int) -> Decimal:
    """Return the customer's outstanding due.

    This is R16 exactly::

        SUM(sales.due_amount WHERE payment_type = 'credit')
        -
        SUM(payments.amount)

    A customer with no credit sales and no payments has a due of ``0.00``.
    """
    credit = _credit_sales_totals(db, customer_id)
    payments = _payment_totals(db, customer_id)
    return _money(credit["due_at_counter"] - payments["total_paid"])


def get_customer_due_breakdown(db: Session, customer_id: int) -> dict[str, Any]:
    """Return the component figures behind a customer's due.

    The breakdown is self-consistent::

        current_due = total_credit_sales - total_paid

    where ``total_credit_sales`` is the gross value sold on credit and
    ``total_paid`` is everything received against those credit sales (the part
    paid at the counter plus every later payment). That makes
    ``current_due`` identical to ``get_customer_due()``.
    """
    credit = _credit_sales_totals(db, customer_id)
    payments = _payment_totals(db, customer_id)

    total_credit_sales = credit["total_credit_sales"]
    total_paid = _money(credit["total_paid_at_counter"] + payments["total_paid"])
    current_due = _money(total_credit_sales - total_paid)

    return {
        "customer_id": customer_id,
        "total_credit_sales": total_credit_sales,
        "total_paid": total_paid,
        "current_due": current_due,
        "sale_count": credit["sale_count"],
        "payment_count": payments["payment_count"],
    }


def get_all_customer_dues(db: Session) -> list[dict[str, Any]]:
    """Return the due breakdown of every customer that has a ledger.

    A customer is included when they have credit sales or payments; a customer
    with neither is omitted so the report shows only real rows. The list is
    sorted by ``current_due`` descending, then by customer name ascending.
    """
    credit = (
        db.query(
            Sale.customer_id.label("customer_id"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total_credit_sales"),
            func.coalesce(func.sum(Sale.paid_amount), 0).label("total_paid_at_counter"),
            func.coalesce(func.sum(Sale.due_amount), 0).label("due_at_counter"),
            func.count(Sale.id).label("sale_count"),
        )
        .filter(Sale.payment_type == "credit", Sale.customer_id.isnot(None))
        .group_by(Sale.customer_id)
        .subquery()
    )

    paid = (
        db.query(
            Payment.customer_id.label("customer_id"),
            func.coalesce(func.sum(Payment.amount), 0).label("total_paid"),
            func.count(Payment.id).label("payment_count"),
        )
        .group_by(Payment.customer_id)
        .subquery()
    )

    rows = (
        db.query(
            Customer.id,
            Customer.name,
            Customer.phone,
            credit.c.total_credit_sales,
            credit.c.total_paid_at_counter,
            credit.c.due_at_counter,
            credit.c.sale_count,
            paid.c.total_paid,
            paid.c.payment_count,
        )
        .outerjoin(credit, credit.c.customer_id == Customer.id)
        .outerjoin(paid, paid.c.customer_id == Customer.id)
        .filter(
            (credit.c.sale_count.isnot(None)) | (paid.c.payment_count.isnot(None))
        )
        .all()
    )

    breakdown: list[dict[str, Any]] = []
    for row in rows:
        total_credit_sales = _money(row.total_credit_sales)
        total_paid = _money(
            (row.total_paid_at_counter or Decimal("0")) + (row.total_paid or Decimal("0"))
        )
        breakdown.append(
            {
                "customer_id": row.id,
                "customer_name": row.name,
                "phone": row.phone,
                "total_credit_sales": total_credit_sales,
                "total_paid": total_paid,
                "current_due": _money(total_credit_sales - total_paid),
                "sale_count": int(row.sale_count or 0),
                "payment_count": int(row.payment_count or 0),
            }
        )

    breakdown.sort(key=lambda item: (-item["current_due"], item["customer_name"] or ""))
    return breakdown


def get_customer_payment_history(db: Session, customer_id: int) -> list[dict[str, Any]]:
    """Return every payment of one customer, newest first.

    Each entry is a plain dict with ``id``, ``customer_id``, ``amount``,
    ``payment_method``, ``note``, ``sale_id`` and ``created_at``.
    """
    payments = (
        db.query(Payment)
        .filter(Payment.customer_id == customer_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )
    return [
        {
            "id": payment.id,
            "customer_id": payment.customer_id,
            "amount": _money(payment.amount),
            "payment_method": payment.payment_method,
            "note": payment.note,
            "sale_id": payment.sale_id,
            "created_at": payment.created_at,
        }
        for payment in payments
    ]


def get_customer_sales(db: Session, customer_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return the sales of one customer, newest first.

    Read-only helper for the customer history endpoint. Each entry carries the
    sale header and the product lines, so a caller can show the whole sale
    without a second round trip.
    """
    sales = (
        db.query(Sale)
        .filter(Sale.customer_id == customer_id)
        .order_by(Sale.created_at.desc(), Sale.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": sale.id,
            "customer_id": sale.customer_id,
            "payment_type": sale.payment_type,
            "total_amount": _money(sale.total_amount),
            "paid_amount": _money(sale.paid_amount),
            "due_amount": _money(sale.due_amount),
            "note": sale.note,
            "created_at": sale.created_at,
            "items": [
                {
                    "id": item.id,
                    "product_id": item.product_id,
                    "product_name": item.product.name if item.product else None,
                    "quantity": item.quantity,
                    "unit_price": _money(item.unit_price),
                    "line_total": _money(item.line_total),
                }
                for item in sale.items
            ],
        }
        for sale in sales
    ]


def get_customer_summary(db: Session, customer_id: int) -> dict[str, Any]:
    """Return the money summary of one customer.

    Read-only helper for the customer history endpoint. ``total_sales`` is
    everything sold on credit, ``total_paid`` is everything received against
    those sales, and ``current_due`` is the remainder.
    """
    breakdown = get_customer_due_breakdown(db, customer_id)
    return {
        "total_sales": breakdown["total_credit_sales"],
        "total_paid": breakdown["total_paid"],
        "current_due": breakdown["current_due"],
    }
