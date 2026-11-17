"""Purchase recording: one transaction that stores a purchase and adds stock.

Owner: Azaz (237).

Recording a purchase is a single database transaction:

1. Validate the supplier exists and is active.
2. Lock every product on the purchase with ``SELECT ... FOR UPDATE``, in
   ascending id order so two concurrent purchases can never deadlock.
3. Validate each product exists and is active.
4. Compute ``line_total = quantity * unit_cost`` and ``total_amount`` in
   ``Decimal`` on the server, and reject a client total that disagrees.
5. Insert the ``purchases`` row and its ``purchase_items`` rows.
6. Increase ``products.current_stock`` and append a ``stock_movements`` row
   (``movement_type="purchase"``, ``reference_type="purchase"``,
   ``reference_id=purchase.id``) with ``balance_after``.
7. Write one audit row through ``audit_service.log_action``.
8. Commit once.

If any step fails, everything is rolled back: no purchase, item, movement,
stock change or audit row survives, and the row locks are released.

Stock note: the lock-and-ledger steps mirror ``app/api/v1/stock.py`` (Zahid)
because that logic is inline in his router and has no reusable service yet.
When a shared ``stock_service`` exists, step 6 should call it instead.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.schemas.purchase import PurchaseCreate
from app.services.audit_service import log_action

ENTITY_TYPE = "purchase"
MONEY_PLACES = Decimal("0.01")

# Largest values that fit the column types (NUMERIC(12,2) and NUMERIC(12,3)).
MAX_MONEY = Decimal("9999999999.99")
MAX_QUANTITY = Decimal("999999999.999")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def record_purchase(
    db: Session, body: PurchaseCreate, user_id: int, ip_address: str | None = None
) -> Purchase:
    """Record a purchase and increase stock, all in one transaction."""
    try:
        purchase = _record_purchase(db, body, user_id, ip_address)
        db.commit()
    except Exception:
        # Also covers validation errors raised after the row locks were taken:
        # the rollback releases them.
        db.rollback()
        raise
    db.refresh(purchase)
    return purchase


def _record_purchase(
    db: Session, body: PurchaseCreate, user_id: int, ip_address: str | None
) -> Purchase:
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier:
        raise _error(status.HTTP_404_NOT_FOUND, "SUPPLIER_NOT_FOUND", "Supplier not found.")
    if not supplier.is_active:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "SUPPLIER_INACTIVE",
            f"Supplier '{supplier.name}' is inactive and cannot receive new purchases.",
        )

    product_ids = sorted(item.product_id for item in body.items)
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

    for product in products:
        if not product.is_active:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "PRODUCT_INACTIVE",
                f"Product '{product.name}' is discontinued and cannot be purchased.",
            )

    # Compute every line on the server; never trust a client total.
    lines: list[tuple[Product, Decimal, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in body.items:
        product = by_id[item.product_id]
        line_total = _money(item.quantity * item.unit_cost)
        if line_total > MAX_MONEY:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "AMOUNT_TOO_LARGE",
                f"The line total for '{product.name}' is too large.",
            )
        if product.current_stock + item.quantity > MAX_QUANTITY:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "STOCK_TOO_LARGE",
                f"Adding {item.quantity} {product.unit} would exceed the maximum stock "
                f"for '{product.name}'.",
            )
        lines.append((product, item.quantity, item.unit_cost, line_total))
        total += line_total

    total = _money(total)
    if total > MAX_MONEY:
        raise _error(status.HTTP_400_BAD_REQUEST, "AMOUNT_TOO_LARGE", "The purchase total is too large.")

    if body.total_amount is not None and _money(body.total_amount) != total:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "TOTAL_MISMATCH",
            f"total_amount {_money(body.total_amount)} does not match the sum of the "
            f"items, {total}.",
        )

    purchase = Purchase(
        supplier_id=supplier.id,
        user_id=user_id,
        invoice_no=body.invoice_no,
        total_amount=total,
        note=body.note,
    )
    db.add(purchase)
    db.flush()  # need purchase.id for the movement reference

    audit_items: list[dict[str, Any]] = []
    for product, quantity, unit_cost, line_total in lines:
        old_stock = product.current_stock
        new_stock = old_stock + quantity

        purchase.items.append(
            PurchaseItem(
                product=product,
                product_id=product.id,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total,
            )
        )

        product.current_stock = new_stock
        db.add(
            StockMovement(
                product_id=product.id,
                user_id=user_id,
                movement_type="purchase",
                quantity=quantity,
                balance_after=new_stock,
                reference_type="purchase",
                reference_id=purchase.id,
                note=f"Purchase #{purchase.id} from {supplier.name}"[:255],
            )
        )

        audit_items.append(
            {
                "product_id": product.id,
                "quantity": str(quantity),
                "unit_cost": str(unit_cost),
                "line_total": str(line_total),
                "stock_before": str(old_stock),
                "stock_after": str(new_stock),
            }
        )

    db.flush()

    log_action(
        db,
        user_id=user_id,
        action="create",
        entity_type=ENTITY_TYPE,
        entity_id=purchase.id,
        new_value={
            "supplier_id": supplier.id,
            "invoice_no": purchase.invoice_no,
            "total_amount": str(total),
            "items": audit_items,
        },
        ip_address=ip_address,
    )
    return purchase


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_purchase(db: Session, purchase_id: int) -> Purchase:
    """Return the purchase with its items, or raise 404."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Purchase not found.")
    return purchase


def list_purchases(
    db: Session,
    *,
    supplier_id: int | None,
    date_from: date | None,
    date_to: date | None,
    skip: int,
    limit: int,
) -> tuple[list[Purchase], int]:
    """List purchases newest first. ``date_to`` is inclusive."""
    query = db.query(Purchase)
    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)
    if date_from is not None:
        query = query.filter(Purchase.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(
            Purchase.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    total = query.count()
    items = (
        query.order_by(Purchase.created_at.desc(), Purchase.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def to_summary(purchase: Purchase) -> dict[str, Any]:
    """Flatten a purchase (without lines) for ``PurchaseSummaryOut``."""
    return {
        "id": purchase.id,
        "supplier_id": purchase.supplier_id,
        "supplier_name": purchase.supplier.name if purchase.supplier else None,
        "user_id": purchase.user_id,
        "invoice_no": purchase.invoice_no,
        "total_amount": purchase.total_amount,
        "item_count": len(purchase.items),
        "note": purchase.note,
        "created_at": purchase.created_at,
    }


def to_detail(purchase: Purchase) -> dict[str, Any]:
    """Flatten a purchase with its lines for ``PurchaseOut``."""
    data = to_summary(purchase)
    data["items"] = [
        {
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product.name if item.product else None,
            "unit": item.product.unit if item.product else None,
            "quantity": item.quantity,
            "unit_cost": item.unit_cost,
            "line_total": item.line_total,
        }
        for item in purchase.items
    ]
    return data
