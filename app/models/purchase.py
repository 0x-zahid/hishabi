"""Purchase model (header of a purchase from a supplier).

Owner: Azaz (237), created with Zahid's approval under ``app/models/``.
Maps to the ``purchases`` table in ``docs/schema.md`` section 3.9.

A purchase is an immutable financial record. It is never updated or deleted;
mistakes are corrected with an owner ``adjustment`` stock movement.

``total_amount`` is ``NUMERIC(12,2)`` and always equals the sum of the
``line_total`` of its items. The server computes it; the client may only
cross-check it.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Purchase(Base):
    """A purchase of one or more products from a supplier."""

    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_purchases_total_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2, asdecimal=True), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")
    items: Mapped[list["PurchaseItem"]] = relationship(
        "PurchaseItem",
        back_populates="purchase",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PurchaseItem.id",
    )

    def __repr__(self) -> str:
        return (
            f"<Purchase id={self.id} supplier_id={self.supplier_id} "
            f"total_amount={self.total_amount}>"
        )


from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
