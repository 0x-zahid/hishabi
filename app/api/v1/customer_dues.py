"""Customer due endpoints.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

These two routes live in their own file because ``app/api/v1/customers.py``
belongs to Azaz (237) and must not be edited. They share the
``/api/v1/customers`` path prefix, so this router is registered **before**
the customers router in ``app/main.py``: Starlette matches routes in
registration order, and the customers router owns a catch-all
``GET /{customer_id}`` that would otherwise swallow ``GET /due``.

Permissions:
- Owner and staff may read the dues: staff work the counter.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.payment import CustomerDueBreakdownOut, CustomerDueListOut
from app.services import dues_service

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["dues"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

require_owner_or_staff = require_roles("owner", "staff")


@router.get(
    "/due",
    response_model=CustomerDueListOut,
    summary="List every customer with an outstanding due",
)
def list_customer_dues(
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Return every customer that has credit sales or payments.

    Largest due first. Customers with no credit sales and no payments are
    omitted, so the list shows only real rows.
    """
    items = dues_service.get_all_customer_dues(db)
    total_due = sum((item["current_due"] for item in items), start=Decimal("0"))
    return {
        "items": items,
        "total": len(items),
        "total_due_amount": total_due.quantize(Decimal("0.01")),
    }


@router.get(
    "/{customer_id}/due",
    response_model=CustomerDueBreakdownOut,
    summary="Get one customer's due breakdown",
    responses={404: {"model": ErrorResponse}},
)
def get_customer_due(
    customer_id: int,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Return how one customer's outstanding due was reached."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found."},
        )
    return dues_service.get_customer_due_breakdown(db, customer_id)
