"""User model.

Owner: Zahid. Maps to the ``users`` table in ``docs/schema.md`` section 3.2.

``password_hash`` stores a bcrypt hash, never a plaintext password. Users are
deactivated (``is_active = false``) rather than deleted, so ``stock_movements``
and ``audit_logs`` keep their referential history.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """An application user, each linked to an optional role."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    role: Mapped["Role | None"] = relationship("Role", lazy="selectin")
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement", back_populates="user", lazy="raise"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


from app.models.audit_log import AuditLog  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
