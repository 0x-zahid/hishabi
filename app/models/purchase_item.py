"""Purchase item model (one product line of a purchase).

Owner: Azaz (237), created with Zahid's approval under ``app/models/``.
Maps to the ``purchase_items`` table in ``docs/schema.md`` section 3.10.

``quantity`` is ``NUMERIC(12,3)``; ``unit_cost`` and ``line_total`` are
``NUMERIC(12,2)``. ``line_total = quantity * unit_cost`` rounded half-up to
two places, computed on the server.

``product_id`` uses ``ON DELETE RESTRICT``: a product that appears on a purchase
must be soft-deleted (``is_active = false``), never removed.
"""

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PurchaseItem(Base):
    """A single product line on a purchase."""

    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_items_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_items_unit_cost_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_purchase_items_line_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchases.id", ondelete="CASCADE"),
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
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)

    purchase: Mapped["Purchase"] = relationship("Purchase", back_populates="items", lazy="raise")
    product: Mapped["Product"] = relationship("Product", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<PurchaseItem id={self.id} purchase_id={self.purchase_id} "
            f"product_id={self.product_id} quantity={self.quantity}>"
        )


from app.models.product import Product  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
