"""Query and filtering service for system audit logs.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.

Security Rule:
Never expose password hashes, tokens, or secrets in the audit payload.
Strip sensitive keys from old_value and new_value before returning.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogDetailOut, AuditLogSummaryOut

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "jwt_secret_key",
}


def sanitize_dict(data: Any) -> Any:
    """Recursively strip sensitive keys from dictionaries and lists."""
    if isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                continue
            clean[k] = sanitize_dict(v)
        return clean
    if isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    return data


def list_audit_logs(
    db: Session,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AuditLogSummaryOut], int]:
    """Query audit logs, newest first, with optional filters."""
    query = db.query(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id)

    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        start_dt = datetime.combine(date_from, time.min)
        query = query.filter(AuditLog.created_at >= start_dt)
    if date_to:
        end_dt = datetime.combine(date_to + timedelta(days=1), time.min)
        query = query.filter(AuditLog.created_at < end_dt)

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []
    for log, uname in rows:
        items.append(
            AuditLogSummaryOut(
                id=log.id,
                user_id=log.user_id,
                username=uname,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )
    return items, total


def get_audit_log_detail(db: Session, log_id: int) -> AuditLogDetailOut:
    """Fetch single audit log entry and sanitize before/after values."""
    row = (
        db.query(AuditLog, User.username)
        .outerjoin(User, AuditLog.user_id == User.id)
        .filter(AuditLog.id == log_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Audit log entry not found."},
        )

    log, uname = row
    return AuditLogDetailOut(
        id=log.id,
        user_id=log.user_id,
        username=uname,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        old_value=sanitize_dict(log.old_value),
        new_value=sanitize_dict(log.new_value),
        ip_address=log.ip_address,
        created_at=log.created_at,
    )
