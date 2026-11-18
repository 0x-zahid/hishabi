"""AI request log model.

Owner: Zahid. Module 3 (AI Bangla entry).
Maps to the ``ai_request_logs`` table.

One row per AI request. The table does three jobs:

1. It counts the daily AI requests of a user, so the limit in
   ``settings.AI_DAILY_LIMIT`` cannot be sidestepped by throwing a proposal
   away (R16).
2. It keeps the raw Bangla input and the raw provider answer, so a strange
   proposal can be traced back to what the model was actually given.
3. It stores the validated proposal, which the user then edits and confirms.

``extracted_data`` is JSONB, so the proposal shape may change without a
migration. A stored proposal is never trusted: it is re-validated when the
user confirms it (R13).

Nothing here stores a customer due. Dues are computed from the sales and
payments tables so there is a single source of truth.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# The four statuses a request row can carry.
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_QUOTA_EXCEEDED = "quota_exceeded"
STATUS_PROVIDER_ERROR = "provider_error"

VALID_STATUSES = (
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_QUOTA_EXCEEDED,
    STATUS_PROVIDER_ERROR,
)

# A request that was actually answered by the model counts against the daily
# limit. A provider outage does not: the user did not spend anything on it.
COUNTED_STATUSES = (STATUS_SUCCESS, STATUS_FAILED)


class AIRequestLog(Base):
    """One AI request and what came of it."""

    __tablename__ = "ai_request_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success','failed','quota_exceeded','provider_error')",
            name="ck_ai_request_logs_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The raw Bangla sentence the user typed.
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    # The raw JSON the provider returned, kept for tracing.
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The validated, database-matched proposal.
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Server-side detail about a failure. Never sent to the client.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User", lazy="raise")

    def __repr__(self) -> str:
        return (
            f"<AIRequestLog id={self.id} user_id={self.user_id} "
            f"status={self.status!r} confirmed={self.confirmed}>"
        )


from app.models.user import User  # noqa: E402
