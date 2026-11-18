"""Sale recording: one transaction that stores a sale and removes stock.

Owner: Zahid. Module 2 (sales and customer dues).

Recording a sale is a single database transaction:

1. Validate the body: at least one item, positive quantities, non-negative
   prices, a known payment type.
2. Validate the customer when one is given, and require one for a credit
   sale.
3. Lock every product on the sale with ``SELECT ... FOR UPDATE``, in ascending
   id order so two concurrent sales can never deadlock.
4. Check the stock of every product against the **summed** quantity of the
   lines that name it, before anything is written.
5. Compute ``line_total = quantity * unit_price`` and ``total_amount`` in
   ``Decimal`` on the server, and reject a client total that disagrees.
6. Insert the ``sales`` row and its ``sale_items`` rows.
7. Decrease ``products.current_stock`` and append a ``stock_movements`` row
   (``movement_type="sale"``, ``reference_type="sale"``,
   ``reference_id=sale.id``) with ``balance_after``.
8. Write one audit row through ``audit_service.log_action``.
9. Commit once.

If any step fails, everything is rolled back: no sale, item, movement, stock
change or audit row survives, and the row locks are released.

Sales are immutable (R19): there is no update and no delete.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.stock_movement import StockMovement
from app.schemas.sale import SaleCreate
from app.services.audit_service import log_action

ENTITY_TYPE = "sale"
MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

CASH = "cash"
CREDIT = "credit"


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def record_sale(
    db: Session, body: SaleCreate, user_id: int, ip_address: str | None = None
) -> Sale:
    """Record a sale and deduct the stock, all in one transaction."""
    try:
        sale = _record_sale(db, body, user_id, ip_address)
        db.commit()
    except Exception:
        # Also covers a failure after the row locks were taken: the rollback
        # releases them.
        db.rollback()
        raise
    db.refresh(sale)
    return sale


def _record_sale(
    db: Session, body: SaleCreate, user_id: int, ip_address: str | None
) -> Sale:
    # --- 1. Body validation (R1 - R4) ------------------------------------
    if not body.items:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_SALE_ITEMS",
            "A sale must contain at least one item.",
        )

    if body.payment_type not in (CASH, CREDIT):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_PAYMENT_TYPE",
            "payment_type must be 'cash' or 'credit'.",
        )

    for item in body.items:
        if item.quantity <= 0:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "INVALID_QUANTITY",
                f"Quantity for product {item.product_id} must be greater than zero.",
            )
        if item.unit_price is not None and item.unit_price < 0:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "INVALID_UNIT_PRICE",
                f"unit_price for product {item.product_id} cannot be negative.",
            )

    # --- 2. Customer validation (R6, R8) ---------------------------------
    customer: Customer | None = None
    if body.customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == body.customer_id).first()
        if not customer:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "CUSTOMER_NOT_FOUND",
                "Customer not found.",
            )
        if not customer.is_active:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "CUSTOMER_INACTIVE",
                f"Customer '{customer.name}' is inactive and cannot be sold to.",
            )
    elif body.payment_type == CREDIT:
        # A credit sale without a customer cannot be tracked.
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "CUSTOMER_REQUIRED",
            "A credit sale must name the customer it is sold to.",
        )

    # --- 3. Lock the product rows (R14) ----------------------------------
    product_ids = sorted({item.product_id for item in body.items})
    products = (
        db.query(Product)
        .filter(Product.id.in_(product_ids))
        .order_by(Product.id.asc())
        .with_for_update()
        .all()
    )
    by_id = {product.id: product for product in products}

    missing = [pid for pid in product_ids if pid not in by_id]
    if missing:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "PRODUCT_NOT_FOUND",
            f"Product(s) not found: {', '.join(str(pid) for pid in missing)}.",
        )

    # --- 4. Stock check before anything is written (R9, R10) -------------
    requested: dict[int, Decimal] = {}
    for item in body.items:
        requested[item.product_id] = requested.get(item.product_id, Decimal("0")) + item.quantity

    for product_id, quantity in requested.items():
        product = by_id[product_id]
        if product.current_stock - quantity < 0:
            raise _error(
                status.HTTP_409_CONFLICT,
                "INSUFFICIENT_STOCK",
                f"Only {product.current_stock} {product.unit} of {product.name} is in stock.",
            )

    # --- 5. Compute the money on the server (R11) -----------------------
    lines: list[tuple[Product, Decimal, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in body.items:
        product = by_id[item.product_id]
        unit_price = product.sale_price if item.unit_price is None else item.unit_price
        line_total = _money(item.quantity * unit_price)
        lines.append((product, _quantity(item.quantity), _money(unit_price), line_total))
        total += line_total

    total = _money(total)

    if body.total_amount is not None and _money(body.total_amount) != total:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "TOTAL_MISMATCH",
            f"total_amount {_money(body.total_amount)} does not match the sum of the "
            f"items, {total}.",
        )

    # --- 6. Work out what was paid and what is due (R5, R7) --------------
    if body.payment_type == CASH:
        if _money(body.paid_amount) != total:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "INVALID_PAID_AMOUNT",
                f"A cash sale must be paid in full: paid_amount must be {total}.",
            )
        paid = total
        due = Decimal("0.00")
    else:
        paid = _money(body.paid_amount)
        if paid < 0:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "INVALID_PAID_AMOUNT",
                "paid_amount cannot be negative.",
            )
        if paid > total:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "INVALID_PAID_AMOUNT",
                f"paid_amount {paid} is larger than the sale total {total}.",
            )
        due = _money(total - paid)

    # --- 7. Write the header, the lines, the stock and the ledger -------
    sale = Sale(
        customer_id=customer.id if customer else None,
        user_id=user_id,
        payment_type=body.payment_type,
        total_amount=total,
        paid_amount=paid,
        due_amount=due,
        note=body.note,
    )
    db.add(sale)
    db.flush()  # need sale.id for the movement reference

    audit_items: list[dict[str, Any]] = []
    for product, quantity, unit_price, line_total in lines:
        sale.items.append(
            SaleItem(
                product=product,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

        new_stock = product.current_stock - quantity
        product.current_stock = new_stock

        db.add(
            StockMovement(
                product_id=product.id,
                user_id=user_id,
                movement_type="sale",
                quantity=quantity,
                balance_after=new_stock,
                reference_type="sale",
                reference_id=sale.id,
                note=f"Sale #{sale.id}"[:255],
            )
        )

        audit_items.append(
            {
                "product_id": product.id,
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            }
        )

    db.flush()

    # --- 8. Audit (R15) --------------------------------------------------
    log_action(
        db,
        user_id=user_id,
        action="create",
        entity_type=ENTITY_TYPE,
        entity_id=sale.id,
        old_value=None,
        new_value={
            "payment_type": sale.payment_type,
            "total_amount": str(total),
            "paid_amount": str(paid),
            "due_amount": str(due),
            "items": audit_items,
        },
        ip_address=ip_address,
    )
    return sale


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_sale(db: Session, sale_id: int) -> Sale:
    """Return the sale with its items, or raise 404."""
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise _error(status.HTTP_404_NOT_FOUND, "SALE_NOT_FOUND", "Sale not found.")
    return sale


def list_sales(
    db: Session,
    *,
    payment_type: str | None,
    customer_id: int | None,
    start_date: date | None,
    end_date: date | None,
    skip: int,
    limit: int,
) -> tuple[list[Sale], int]:
    """List sales newest first. ``end_date`` is inclusive."""
    query = db.query(Sale)
    if payment_type is not None:
        query = query.filter(Sale.payment_type == payment_type)
    if customer_id is not None:
        query = query.filter(Sale.customer_id == customer_id)
    if start_date is not None:
        query = query.filter(Sale.created_at >= datetime.combine(start_date, time.min))
    if end_date is not None:
        query = query.filter(
            Sale.created_at < datetime.combine(end_date + timedelta(days=1), time.min)
        )
    total = query.count()
    items = (
        query.order_by(Sale.created_at.desc(), Sale.id.desc()).offset(skip).limit(limit).all()
    )
    return items, total


def to_summary(sale: Sale) -> dict[str, Any]:
    """Flatten a sale (with its lines) for the list endpoint."""
    return {
        "id": sale.id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer.name if sale.customer else None,
        "user_id": sale.user_id,
        "payment_type": sale.payment_type,
        "total_amount": sale.total_amount,
        "paid_amount": sale.paid_amount,
        "due_amount": sale.due_amount,
        "item_count": len(sale.items),
        "note": sale.note,
        "created_at": sale.created_at,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "unit": item.product.unit if item.product else None,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
            }
            for item in sale.items
        ],
    }


def to_detail(sale: Sale) -> dict[str, Any]:
    """Flatten a sale with its lines and its payments."""
    data = to_summary(sale)
    data["payments"] = [
        {
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
        for payment in sale.payments
    ]
    return data
