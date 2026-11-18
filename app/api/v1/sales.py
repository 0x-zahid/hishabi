"""Sale recording and reading endpoints.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

Permissions:
- Owner and staff may record sales and read them: staff work the counter.

Recording a sale is a single database transaction (sale + lines + stock
deduction + stock ledger + audit row). It lives in
``app/services/sale_service.py``; this file only translates HTTP to and from
that service.

Sales are immutable: there is no update and no delete. A mistake is corrected
with a reversing entry.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.sale import SaleCreate, SaleListOut, SaleOut
from app.services import sale_service

router = APIRouter(
    prefix="/api/v1/sales",
    tags=["sales"],
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
    response_model=SaleOut,
    summary="Record a sale and deduct the stock",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def create_sale(
    body: SaleCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Record a multi-item sale.

    Stock for every product decreases by the sold quantity and a ``sale``
    stock movement is written per item. Totals are computed on the server;
    ``total_amount`` in the body is an optional cross-check.
    """
    ip = request.client.host if request.client else None
    sale = sale_service.record_sale(db, body, current_user.id, ip)
    return sale_service.to_detail(sale)


@router.get(
    "",
    response_model=SaleListOut,
    summary="List sales",
)
def list_sales(
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(20, ge=1, le=100, description="Rows per page"),
    payment_type: str | None = Query(None, description="Filter by 'cash' or 'credit'"),
    customer_id: int | None = Query(None, gt=0),
    start_date: date | None = Query(None, description="Inclusive, YYYY-MM-DD"),
    end_date: date | None = Query(None, description="Inclusive, YYYY-MM-DD"),
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """List sales newest first, optionally filtered."""
    if payment_type is not None and payment_type not in ("cash", "credit"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_PAYMENT_TYPE",
                "message": "payment_type must be 'cash' or 'credit'.",
            },
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_DATE_RANGE",
                "message": "start_date must be on or before end_date.",
            },
        )

    items, total = sale_service.list_sales(
        db,
        payment_type=payment_type,
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return {"items": [sale_service.to_detail(sale) for sale in items], "total": total}


@router.get(
    "/{sale_id}",
    response_model=SaleOut,
    summary="Get a sale with its items and payments",
    responses={404: {"model": ErrorResponse}},
)
def get_sale(
    sale_id: int,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    return sale_service.to_detail(sale_service.get_sale(db, sale_id))
