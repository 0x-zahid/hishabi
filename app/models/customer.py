"""Customer model.

Owner: Azaz (237), created with Zahid's approval under ``app/models/``.
Maps to the ``customers`` table in ``docs/schema.md`` section 3.7.

A customer is a person the shop sells to. Customers are deactivated
(``is_active = false``) rather than deleted, so sales, dues and payments that
reference them (Zahid's module) keep their history.

Dues are deliberately **not** stored here: they are computed from the sales and
payments tables so there is a single source of truth.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Customer(Base):
    """A customer of the shop."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
        return f"<Customer id={self.id} name={self.name!r}>"
