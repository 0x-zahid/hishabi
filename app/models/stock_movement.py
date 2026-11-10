"""Stock movement model.

Owner: Zahid. Maps to the ``stock_movements`` table in ``docs/schema.md``
section 3.5.

This table is an immutable ledger of stock in and out events. Rows are
appended, never updated or deleted, so a product's history can be
reconstructed from the ledger alone.

``balance_after`` is denormalised on purpose: it stores the stock level at the
moment of the movement so history does not need recomputation
(``docs/schema.md`` section 9, note 7).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockMovement(Base):
    """A single stock in, out or adjust event for a product."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    movement_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3, asdecimal=True), nullable=False
    )
    balance_after: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3, asdecimal=True), nullable=True
    )
    reference_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    product: Mapped["Product | None"] = relationship(
        "Product", back_populates="stock_movements", lazy="raise"
    )
    user: Mapped["User | None"] = relationship(
        "User", back_populates="stock_movements", lazy="raise"
    )

    def __repr__(self) -> str:
        return (
            f"<StockMovement id={self.id} product_id={self.product_id} "
            f"type={self.movement_type!r} quantity={self.quantity}>"
        )


from app.models.product import Product  # noqa: E402
from app.models.user import User  # noqa: E402
