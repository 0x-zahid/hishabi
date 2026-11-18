"""Sale item model (one product line of a sale).

Owner: Zahid. Maps to the ``sale_items`` table in ``docs/schema.md`` section 3.12.

``quantity`` is ``NUMERIC(12,3)``; ``unit_price`` and ``line_total`` are
``NUMERIC(12,2)``. ``line_total = quantity * unit_price`` rounded half-up to
two places, computed on the server.

``product_id`` uses ``ON DELETE RESTRICT``: a product that appears on a sale
must be soft-deleted (``is_active = false``), never removed.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SaleItem(Base):
    """A single product line on a sale."""

    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_sale_items_line_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3, asdecimal=True), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    sale: Mapped["Sale"] = relationship("Sale", back_populates="items", lazy="raise")
    product: Mapped["Product"] = relationship("Product", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<SaleItem id={self.id} product_id={self.product_id} "
            f"quantity={self.quantity}>"
        )


from app.models.product import Product  # noqa: E402
from app.models.sale import Sale  # noqa: E402
