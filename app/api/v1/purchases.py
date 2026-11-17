"""Purchase recording endpoints.

Owner: Azaz (237). Complies with PROJECT_RULES.md and docs/schema.md.

Permissions:
- Owner and staff can record purchases.
- Any authenticated user can list and read purchases.

Purchases are immutable: there is no update or delete. A mistake is corrected
with an owner ``adjustment`` stock movement.

The transaction (purchase + items + stock increase + stock movements + audit
row, all-or-nothing) lives in ``app/services/purchase_service.py``.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.purchase import PurchaseCreate, PurchaseListOut, PurchaseOut
from app.services import purchase_service

router = APIRouter(
    prefix="/api/v1/purchases",
    tags=["purchases"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

require_owner_or_staff = require_roles("owner", "staff")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOut,
    summary="Record a purchase from a supplier and increase stock",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_purchase(
    body: PurchaseCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Record a multi-item purchase.

    Stock for every product increases by the purchased quantity and a
    ``purchase`` stock movement is written per item. Totals are computed on the
    server; ``total_amount`` in the body is an optional cross-check.
    """
    ip = request.client.host if request.client else None
    purchase = purchase_service.record_purchase(db, body, current_user.id, ip)
    return purchase_service.to_detail(purchase)


@router.get(
    "",
    response_model=PurchaseListOut,
    summary="List purchases",
)
def list_purchases(
    supplier_id: int | None = Query(None, gt=0),
    date_from: date | None = Query(None, description="Inclusive, YYYY-MM-DD"),
    date_to: date | None = Query(None, description="Inclusive, YYYY-MM-DD"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List purchases newest first, optionally filtered by supplier and date range."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DATE_RANGE", "message": "date_from must be on or before date_to."},
        )
    items, total = purchase_service.list_purchases(
        db,
        supplier_id=supplier_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )
    return {"items": [purchase_service.to_summary(p) for p in items], "total": total}


@router.get(
    "/{purchase_id}",
    response_model=PurchaseOut,
    summary="Get a purchase with its items",
    responses={404: {"model": ErrorResponse}},
)
def get_purchase(
    purchase_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return purchase_service.to_detail(purchase_service.get_purchase(db, purchase_id))
