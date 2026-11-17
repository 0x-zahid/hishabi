"""Audit log viewer endpoints.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md:
- Owner only: Staff or Viewer receive 403.
- Passwords and sensitive keys are stripped from responses.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_owner
from app.core.database import get_db
from app.models.user import User
from app.schemas.audit import AuditLogDetailOut, AuditLogListOut
from app.schemas.common import ErrorResponse
from app.services import audit_query_service

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


@router.get(
    "",
    response_model=AuditLogListOut,
    summary="List and filter audit logs (Owner only)",
)
def list_audit_logs(
    action: str | None = Query(None, max_length=40, description="Filter by action (e.g. create, update, delete)"),
    entity_type: str | None = Query(None, max_length=40, description="Filter by entity (e.g. product, customer, purchase)"),
    user_id: int | None = Query(None, gt=0, description="Filter by user id"),
    date_from: date | None = Query(None, description="Start date (inclusive, YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="End date (inclusive, YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return paginated audit log entries, newest first."""
    items, total = audit_query_service.list_audit_logs(
        db,
        action=action,
        entity_type=entity_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )
    return AuditLogListOut(items=items, total=total)


@router.get(
    "/{log_id}",
    response_model=AuditLogDetailOut,
    summary="Get audit log entry details (Owner only)",
    responses={404: {"model": ErrorResponse}},
)
def get_audit_log_detail(
    log_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return single audit log entry with sanitized before and after snapshots."""
    return audit_query_service.get_audit_log_detail(db, log_id)
