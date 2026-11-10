"""Audit log model.

Owner: Zahid. Maps to the ``audit_logs`` table in ``docs/schema.md`` section 3.6.

Every row is a before/after snapshot of a change made to some entity.
``old_value`` and ``new_value`` are JSONB so any entity shape can be stored
without a schema change.

Audit rows are permanent evidence and outlive the user who made the change:
``users.id`` uses ``ON DELETE SET NULL`` and no cascade ever removes a row
(``docs/schema.md`` section 4).

``entity_id`` deliberately carries no foreign key because it spans multiple
entity types; ``entity_type`` supplies the discriminator
(``docs/schema.md`` section 9, note 6).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuditLog(Base):
    """A recorded change to an entity, with the before and after state."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship(
        "User", back_populates="audit_logs", lazy="raise"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"entity_type={self.entity_type!r} entity_id={self.entity_id}>"
        )


from app.models.user import User  # noqa: E402
