"""Audit logging helper.

Owner: Zahid. This module is shared by every module that records a critical
action, so the ``log_action`` signature is stable: product create, update and
delete, stock movement, sale, payment, purchase and role change all call it
(PROJECT_RULES.md, "Audit logging").

The helper adds the row to the session and flushes it so the generated id and
timestamp are available to the caller. It does **not** commit: the audit row
belongs to the caller's transaction, so it rolls back with the change it
describes and never survives a failed operation.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Record a change in ``audit_logs`` and return the pending row.

    ``old_value`` and ``new_value`` are JSONB snapshots of the entity before
    and after the change; pass ``None`` when there is no prior state (a
    create) or no resulting state (a delete).
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
    return entry
