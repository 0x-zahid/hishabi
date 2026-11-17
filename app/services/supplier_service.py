"""Supplier business logic and queries.

Owner: Azaz (237). PROJECT_RULES.md: no SQL in endpoint files, so every
supplier query lives here and the router stays thin.

Every write records an audit row through ``audit_service.log_action`` inside
the same transaction. Failures raise ``HTTPException`` with a detail in the
shared ``{"code", "message"}`` shape.
"""

from decimal import Decimal
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.purchase import Purchase
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.services.audit_service import log_action
from app.services.customer_service import escape_like

ENTITY_TYPE = "supplier"


def _snapshot(supplier: Supplier) -> dict[str, Any]:
    """JSON-safe snapshot of a supplier for the audit log."""
    return {
        "name": supplier.name,
        "phone": supplier.phone,
        "email": supplier.email,
        "contact_person": supplier.contact_person,
        "address": supplier.address,
        "note": supplier.note,
        "is_active": supplier.is_active,
    }


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": "Supplier not found."},
    )


def _phone_taken(phone: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "PHONE_EXISTS",
            "message": f"A supplier with phone {phone} already exists.",
        },
    )


def _ensure_phone_free(db: Session, phone: str | None, exclude_id: int | None = None) -> None:
    if not phone:
        return
    query = db.query(Supplier.id).filter(Supplier.phone == phone)
    if exclude_id is not None:
        query = query.filter(Supplier.id != exclude_id)
    if query.first():
        raise _phone_taken(phone)


def _save(db: Session, phone: str | None, work: Callable[[], None]) -> None:
    """Run ``work`` and commit as one unit.

    A phone-uniqueness race can surface at ``flush`` or ``commit``; either way it
    becomes a clean 409 and the transaction is rolled back.
    """
    try:
        work()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _phone_taken(phone or "")
    except Exception:
        db.rollback()
        raise


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    """Return the supplier or raise 404."""
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise _not_found()
    return supplier


def get_supplier_stats(db: Session, supplier_id: int) -> tuple[int, Decimal]:
    """Return ``(purchase_count, total_purchased)`` for a supplier."""
    count, total = (
        db.query(func.count(Purchase.id), func.coalesce(func.sum(Purchase.total_amount), 0))
        .filter(Purchase.supplier_id == supplier_id)
        .one()
    )
    return int(count), Decimal(total)


def list_suppliers(
    db: Session,
    *,
    search: str | None,
    is_active: bool | None,
    skip: int,
    limit: int,
) -> tuple[list[Supplier], int]:
    """List suppliers, optionally filtered by search and status.

    The search matches name, phone or contact person.
    """
    query = db.query(Supplier)
    if is_active is not None:
        query = query.filter(Supplier.is_active.is_(is_active))
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.filter(
            or_(
                Supplier.name.ilike(pattern, escape="\\"),
                Supplier.phone.ilike(pattern, escape="\\"),
                Supplier.contact_person.ilike(pattern, escape="\\"),
            )
        )
    total = query.count()
    items = query.order_by(Supplier.name.asc(), Supplier.id.asc()).offset(skip).limit(limit).all()
    return items, total


def create_supplier(
    db: Session, body: SupplierCreate, user_id: int, ip_address: str | None = None
) -> Supplier:
    """Create a supplier and audit it in one transaction."""
    _ensure_phone_free(db, body.phone)

    supplier = Supplier(**body.model_dump(), is_active=True)

    def _work() -> None:
        db.add(supplier)
        db.flush()
        log_action(
            db,
            user_id=user_id,
            action="create",
            entity_type=ENTITY_TYPE,
            entity_id=supplier.id,
            new_value=_snapshot(supplier),
            ip_address=ip_address,
        )

    _save(db, body.phone, _work)
    db.refresh(supplier)
    return supplier


def update_supplier(
    db: Session,
    supplier_id: int,
    body: SupplierUpdate,
    user_id: int,
    ip_address: str | None = None,
) -> Supplier:
    """Apply a partial update and audit the before/after state."""
    supplier = get_supplier(db, supplier_id)
    changes = body.model_dump(exclude_unset=True)

    if "phone" in changes:
        _ensure_phone_free(db, changes["phone"], exclude_id=supplier.id)

    before = _snapshot(supplier)
    for field, value in changes.items():
        setattr(supplier, field, value)
    after = _snapshot(supplier)

    if before == after:
        return supplier

    def _work() -> None:
        log_action(
            db,
            user_id=user_id,
            action="update",
            entity_type=ENTITY_TYPE,
            entity_id=supplier.id,
            old_value=before,
            new_value=after,
            ip_address=ip_address,
        )

    _save(db, supplier.phone, _work)
    db.refresh(supplier)
    return supplier


def deactivate_supplier(
    db: Session, supplier_id: int, user_id: int, ip_address: str | None = None
) -> Supplier:
    """Soft-delete a supplier (``is_active = false``) and audit it."""
    supplier = get_supplier(db, supplier_id)
    if not supplier.is_active:
        return supplier

    before = _snapshot(supplier)
    supplier.is_active = False
    try:
        log_action(
            db,
            user_id=user_id,
            action="delete",
            entity_type=ENTITY_TYPE,
            entity_id=supplier.id,
            old_value=before,
            new_value=_snapshot(supplier),
            ip_address=ip_address,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(supplier)
    return supplier
