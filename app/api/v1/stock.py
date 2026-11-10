"""Stock movement endpoints: record stock in and out, and list movements.

Owner: Zahid. Complies with PROJECT_RULES.md and docs/schema.md.

Recording a movement is a single database transaction:

1. Lock the product row with ``SELECT ... FOR UPDATE``.
2. Validate that the new quantity never goes below zero.
3. Insert the ``stock_movements`` row with ``balance_after``.
4. Update ``products.current_stock``.
5. Write an audit row.

If any step fails the whole thing is rolled back, so the ledger and the
product can never disagree.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_role_name
from app.core.database import get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.schemas.stock import (
    LowStockListOut,
    LowStockProductOut,
    StockMessageResponse,
    StockMovementCreate,
    StockMovementListOut,
    StockMovementOut,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1", tags=["stock"])

# Roles that may record a stock movement.
ALLOWED_ROLES = {"owner", "staff"}
# Only an owner may post a manual adjustment.
OWNER_ONLY_TYPES = {"adjustment"}


def _api_error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return an error response in the shared PROJECT_RULES.md shape."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _delta_for(movement_type: str, quantity: Decimal) -> Decimal:
    """Return the signed change to stock for a movement.

    ``purchase`` and ``return`` add stock, ``sale`` removes it, and an
    ``adjustment`` carries its direction in the sign of the quantity.
    """
    if movement_type in ("purchase", "return"):
        return quantity
    if movement_type == "sale":
        return -quantity
    return quantity  # adjustment: the sign is already in the body


@router.get(
    "/stock-movements",
    status_code=status.HTTP_200_OK,
    response_model=StockMovementListOut,
    summary="List stock movements",
)
def list_stock_movements(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    product_id: int | None = Query(None, gt=0),
    movement_type: str | None = Query(None, max_length=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List stock movements, newest first, optionally filtered."""
    query = db.query(StockMovement)

    if product_id is not None:
        query = query.filter(StockMovement.product_id == product_id)

    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)

    total = query.count()
    items = query.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).offset(skip).limit(limit).all()

    return StockMovementListOut(items=items, total=total)


@router.get(
    "/low-stock",
    status_code=status.HTTP_200_OK,
    response_model=LowStockListOut,
    summary="List products at or below their low-stock threshold",
)
def list_low_stock_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active products whose current stock has reached the threshold."""
    query = db.query(Product).filter(
        Product.is_active.is_(True),
        Product.current_stock <= Product.low_stock_threshold,
    )
    items = query.order_by(Product.id.asc()).all()

    return LowStockListOut(items=items, total=len(items))


@router.post(
    "/stock-movements",
    status_code=status.HTTP_201_CREATED,
    response_model=StockMovementOut,
    summary="Record a stock movement",
)
def create_stock_movement(
    body: StockMovementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a stock movement and update the product's stock level.

    Owners and staff may record movements. Only an owner may post a manual
    adjustment. The movement, the updated stock and the audit row are written
    in one transaction.
    """
    role_name = get_role_name(current_user, db)

    if role_name not in ALLOWED_ROLES:
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Owner or staff permissions are required to record stock movements.",
        )

    if body.movement_type in OWNER_ONLY_TYPES and role_name != "owner":
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Only an owner can record a manual stock adjustment.",
        )

    # Lock the product row so two concurrent movements cannot both read the
    # same starting stock and overwrite each other.
    product = (
        db.query(Product)
        .filter(Product.id == body.product_id)
        .with_for_update()
        .first()
    )
    if not product:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Product not found.",
        )

    if not product.is_active:
        return _api_error(
            status.HTTP_400_BAD_REQUEST,
            "PRODUCT_INACTIVE",
            f"Product '{product.name}' is discontinued and cannot receive stock movements.",
        )

    delta = _delta_for(body.movement_type, body.quantity)
    new_stock = product.current_stock + delta

    if new_stock < 0:
        return _api_error(
            status.HTTP_400_BAD_REQUEST,
            "INSUFFICIENT_STOCK",
            (
                f"Only {product.current_stock} {product.unit} of {product.name} "
                "is in stock."
            ),
        )

    old_stock = product.current_stock

    try:
        movement = StockMovement(
            product_id=product.id,
            user_id=current_user.id,
            movement_type=body.movement_type,
            quantity=body.quantity,
            balance_after=new_stock,
            reference_type=None,
            reference_id=None,
            note=body.note,
        )
        db.add(movement)

        product.current_stock = new_stock
        product.updated_at = func.now()

        log_action(
            db,
            user_id=current_user.id,
            action="stock_movement",
            entity_type="stock_movement",
            entity_id=None,
            old_value={
                "product_id": product.id,
                "current_stock": str(old_stock),
            },
            new_value={
                "product_id": product.id,
                "current_stock": str(new_stock),
                "movement_type": body.movement_type,
                "quantity": str(body.quantity),
            },
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(movement)

    return movement
