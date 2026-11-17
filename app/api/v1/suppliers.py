"""Supplier management endpoints.

Owner: Azaz (237). Complies with PROJECT_RULES.md and docs/schema.md.

Permissions:
- Any authenticated user can list and read suppliers and their purchases.
- Owner and staff can create and update suppliers.
- Only an owner can deactivate (soft-delete) a supplier.

All queries live in ``app/services/supplier_service.py``.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_owner, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.purchase import PurchaseListOut
from app.schemas.supplier import (
    SupplierCreate,
    SupplierDetailOut,
    SupplierListOut,
    SupplierMessageResponse,
    SupplierOut,
    SupplierUpdate,
)
from app.services import purchase_service, supplier_service

router = APIRouter(
    prefix="/api/v1/suppliers",
    tags=["suppliers"],
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
    response_model=SupplierOut,
    summary="Create a supplier",
    responses={409: {"model": ErrorResponse}},
)
def create_supplier(
    body: SupplierCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Create a supplier. Phone numbers must be unique when given."""
    return supplier_service.create_supplier(db, body, current_user.id, _client_ip(request))


@router.get(
    "",
    response_model=SupplierListOut,
    summary="List and search suppliers",
)
def list_suppliers(
    search: str | None = Query(
        None, max_length=120, description="Match name, phone or contact person"
    ),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = supplier_service.list_suppliers(
        db, search=search, is_active=is_active, skip=skip, limit=limit
    )
    return SupplierListOut(items=items, total=total)


@router.get(
    "/{supplier_id}",
    response_model=SupplierDetailOut,
    summary="Get a supplier profile with purchase statistics",
    responses={404: {"model": ErrorResponse}},
)
def get_supplier(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    supplier = supplier_service.get_supplier(db, supplier_id)
    count, total = supplier_service.get_supplier_stats(db, supplier.id)
    data = SupplierOut.model_validate(supplier).model_dump()
    return SupplierDetailOut(**data, purchase_count=count, total_purchased=total)


@router.get(
    "/{supplier_id}/purchases",
    response_model=PurchaseListOut,
    summary="List purchases from a supplier",
    responses={404: {"model": ErrorResponse}},
)
def list_supplier_purchases(
    supplier_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    supplier_service.get_supplier(db, supplier_id)  # 404 if missing
    items, total = purchase_service.list_purchases(
        db, supplier_id=supplier_id, date_from=None, date_to=None, skip=skip, limit=limit
    )
    return {"items": [purchase_service.to_summary(p) for p in items], "total": total}


@router.patch(
    "/{supplier_id}",
    response_model=SupplierOut,
    summary="Update a supplier",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
@router.put(
    "/{supplier_id}",
    response_model=SupplierOut,
    summary="Update a supplier (alias of PATCH)",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    include_in_schema=False,
)
def update_supplier(
    supplier_id: int,
    body: SupplierUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    return supplier_service.update_supplier(
        db, supplier_id, body, current_user.id, _client_ip(request)
    )


@router.delete(
    "/{supplier_id}",
    response_model=SupplierMessageResponse,
    summary="Deactivate a supplier (owner only)",
    responses={404: {"model": ErrorResponse}},
)
def deactivate_supplier(
    supplier_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Soft-delete: the supplier is marked inactive, purchase history is kept."""
    supplier = supplier_service.deactivate_supplier(
        db, supplier_id, current_user.id, _client_ip(request)
    )
    return SupplierMessageResponse(message=f"Supplier '{supplier.name}' deactivated.")
