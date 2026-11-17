"""Customer business logic and queries.

Owner: Azaz (237). PROJECT_RULES.md: no SQL in endpoint files, so every
customer query lives here and the router stays thin.

Every write (create, update, deactivate) records an audit row through
``audit_service.log_action`` inside the same transaction, so the audit row and
the change commit or roll back together.

Failures raise ``HTTPException`` whose detail is already in the shared
``{"code", "message"}`` shape, the same convention as ``app/api/deps.py``.
"""

from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.audit_service import log_action

ENTITY_TYPE = "customer"


def escape_like(term: str) -> str:
    """Escape ``%``, ``_`` and ``\\`` so a search term is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snapshot(customer: Customer) -> dict[str, Any]:
    """JSON-safe snapshot of a customer for the audit log."""
    return {
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "note": customer.note,
        "is_active": customer.is_active,
    }


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": "Customer not found."},
    )


def _phone_taken(phone: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "PHONE_EXISTS",
            "message": f"A customer with phone {phone} already exists.",
        },
    )


def _ensure_phone_free(db: Session, phone: str | None, exclude_id: int | None = None) -> None:
    if not phone:
        return
    query = db.query(Customer.id).filter(Customer.phone == phone)
    if exclude_id is not None:
        query = query.filter(Customer.id != exclude_id)
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


def get_customer(db: Session, customer_id: int) -> Customer:
    """Return the customer or raise 404."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise _not_found()
    return customer


def list_customers(
    db: Session,
    *,
    search: str | None,
    is_active: bool | None,
    skip: int,
    limit: int,
) -> tuple[list[Customer], int]:
    """List customers, optionally filtered by name/phone search and status."""
    query = db.query(Customer)
    if is_active is not None:
        query = query.filter(Customer.is_active.is_(is_active))
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.filter(
            or_(
                Customer.name.ilike(pattern, escape="\\"),
                Customer.phone.ilike(pattern, escape="\\"),
            )
        )
    total = query.count()
    items = query.order_by(Customer.name.asc(), Customer.id.asc()).offset(skip).limit(limit).all()
    return items, total


def create_customer(
    db: Session, body: CustomerCreate, user_id: int, ip_address: str | None = None
) -> Customer:
    """Create a customer and audit it in one transaction."""
    _ensure_phone_free(db, body.phone)

    customer = Customer(**body.model_dump(), is_active=True)

    def _work() -> None:
        db.add(customer)
        db.flush()
        log_action(
            db,
            user_id=user_id,
            action="create",
            entity_type=ENTITY_TYPE,
            entity_id=customer.id,
            new_value=_snapshot(customer),
            ip_address=ip_address,
        )

    _save(db, body.phone, _work)
    db.refresh(customer)
    return customer


def update_customer(
    db: Session,
    customer_id: int,
    body: CustomerUpdate,
    user_id: int,
    ip_address: str | None = None,
) -> Customer:
    """Apply a partial update and audit the before/after state."""
    customer = get_customer(db, customer_id)
    changes = body.model_dump(exclude_unset=True)

    if "phone" in changes:
        _ensure_phone_free(db, changes["phone"], exclude_id=customer.id)

    before = _snapshot(customer)
    for field, value in changes.items():
        setattr(customer, field, value)
    after = _snapshot(customer)

    if before == after:
        return customer

    def _work() -> None:
        log_action(
            db,
            user_id=user_id,
            action="update",
            entity_type=ENTITY_TYPE,
            entity_id=customer.id,
            old_value=before,
            new_value=after,
            ip_address=ip_address,
        )

    _save(db, customer.phone, _work)
    db.refresh(customer)
    return customer


def deactivate_customer(
    db: Session, customer_id: int, user_id: int, ip_address: str | None = None
) -> Customer:
    """Soft-delete a customer (``is_active = false``) and audit it."""
    customer = get_customer(db, customer_id)
    if not customer.is_active:
        return customer

    before = _snapshot(customer)
    customer.is_active = False
    try:
        log_action(
            db,
            user_id=user_id,
            action="delete",
            entity_type=ENTITY_TYPE,
            entity_id=customer.id,
            old_value=before,
            new_value=_snapshot(customer),
            ip_address=ip_address,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(customer)
    return customer


def get_customer_history(db: Session, customer_id: int, activity_limit: int) -> dict[str, Any]:
    """Return the customer profile with its history.

    ``recent_activity`` comes from ``audit_logs``. Sales, payments and dues are
    owned by Zahid's module and their tables do not exist yet, so ``sales``,
    ``payments`` and ``summary`` are empty/zero until his read-only helper is
    available to call from here.
    """
    customer = get_customer(db, customer_id)
    activity = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == ENTITY_TYPE, AuditLog.entity_id == customer.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(activity_limit)
        .all()
    )
    return {
        "customer": customer,
        "sales": [],
        "payments": [],
        "recent_activity": activity,
    }
