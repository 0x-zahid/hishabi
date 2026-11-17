"""Customer management endpoints.

Owner: Azaz (237). Complies with PROJECT_RULES.md and docs/schema.md.

Permissions:
- Any authenticated user can list and read customers.
- Owner and staff can create and update customers.
- Only an owner can deactivate (soft-delete) a customer.

All queries live in ``app/services/customer_service.py``.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_owner, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.customer import (
    CustomerCreate,
    CustomerHistoryOut,
    CustomerListOut,
    CustomerMessageResponse,
    CustomerOut,
    CustomerUpdate,
)
from app.services import customer_service

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["customers"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

require_owner_or_staff = require_roles("owner", "staff")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomerOut,
    summary="Create a customer",
    responses={409: {"model": ErrorResponse}},
)
def create_customer(
    body: CustomerCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Create a customer. Phone numbers must be unique when given."""
    return customer_service.create_customer(db, body, current_user.id, _client_ip(request))


@router.get(
    "",
    response_model=CustomerListOut,
    summary="List and search customers",
)
def list_customers(
    search: str | None = Query(None, max_length=120, description="Match name or phone"),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List customers alphabetically, optionally filtered."""
    items, total = customer_service.list_customers(
        db, search=search, is_active=is_active, skip=skip, limit=limit
    )
    return CustomerListOut(items=items, total=total)


@router.get(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Get a customer profile",
    responses={404: {"model": ErrorResponse}},
)
def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return customer_service.get_customer(db, customer_id)


@router.get(
    "/{customer_id}/history",
    response_model=CustomerHistoryOut,
    summary="Get a customer's purchases, dues, payments and recent activity",
    responses={404: {"model": ErrorResponse}},
)
def get_customer_history(
    customer_id: int,
    limit: int = Query(20, ge=1, le=100, description="Max recent-activity entries"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the profile plus history.

    ``sales``, ``payments`` and ``summary`` are provided by the sales/payments
    module (Zahid) and stay empty/zero until that module is merged.
    """
    return customer_service.get_customer_history(db, customer_id, limit)


@router.patch(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Update a customer",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
@router.put(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Update a customer (alias of PATCH)",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    include_in_schema=False,
)
def update_customer(
    customer_id: int,
    body: CustomerUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Partially update a customer. Only the fields sent are changed."""
    return customer_service.update_customer(
        db, customer_id, body, current_user.id, _client_ip(request)
    )


@router.delete(
    "/{customer_id}",
    response_model=CustomerMessageResponse,
    summary="Deactivate a customer (owner only)",
    responses={404: {"model": ErrorResponse}},
)
def deactivate_customer(
    customer_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Soft-delete: the customer is marked inactive, history is kept."""
    customer = customer_service.deactivate_customer(
        db, customer_id, current_user.id, _client_ip(request)
    )
    return CustomerMessageResponse(message=f"Customer '{customer.name}' deactivated.")
