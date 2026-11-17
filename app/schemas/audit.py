"""Request and response schemas for system audit logs.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogDetailOut(BaseModel):
    """Full detail of an audit log entry with before and after state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str | None = None
    action: str | None
    entity_type: str | None
    entity_id: int | None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class AuditLogSummaryOut(BaseModel):
    """Summary of an audit log entry for table listing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str | None = None
    action: str | None
    entity_type: str | None
    entity_id: int | None
    ip_address: str | None = None
    created_at: datetime


class AuditLogListOut(BaseModel):
    """Paginated list of audit logs in standard items/total shape."""

    items: list[AuditLogSummaryOut]
    total: int
