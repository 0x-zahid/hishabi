"""Customer payment endpoints.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

Permissions:
- Owner and staff may take payments and read them: staff work the counter.

Recording a payment is a single database transaction (payment + audit row).
It lives in ``app/services/payment_service.py``.

Payments are immutable: there is no update and no delete.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.payment import PaymentCreate, PaymentListOut, PaymentOut
from app.services import payment_service

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
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
    response_model=PaymentOut,
    summary="Record a payment against a customer due",
    responses={404: {"model": ErrorResponse}},
)
def create_payment(
    body: PaymentCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Record a payment.

    The customer's due is computed, never stored, so the payment is checked
    against the outstanding due before it is written.
    """
    ip = request.client.host if request.client else None
    payment = payment_service.record_payment(db, body, current_user.id, ip)
    return payment_service.to_summary(payment)


@router.get(
    "",
    response_model=PaymentListOut,
    summary="List the payment history of a customer",
)
def list_payments(
    customer_id: int = Query(..., gt=0, description="The customer whose history is listed"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(20, ge=1, le=100, description="Rows per page"),
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Return the payments of one customer, newest first."""
    if db.query(Customer).filter(Customer.id == customer_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found."},
        )

    # The history comes from the shared dues service, so the endpoint and
    # ``dues_service.get_customer_payment_history()`` can never disagree.
    items, total = payment_service.history_page(
        db, customer_id=customer_id, skip=(page - 1) * page_size, limit=page_size
    )
    return {"items": items, "total": total}
