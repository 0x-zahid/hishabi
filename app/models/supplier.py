"""Supplier model.

Owner: Azaz (237), created with Zahid's approval under ``app/models/``.
Maps to the ``suppliers`` table in ``docs/schema.md`` section 3.8.

Suppliers are deactivated rather than deleted: ``purchases.supplier_id`` uses
``ON DELETE RESTRICT`` so purchase history can never lose its supplier.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Supplier(Base):
    """A supplier the shop buys stock from."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} name={self.name!r}>"
