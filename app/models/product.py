"""Product model.

Owner: Zahid. Maps to the ``products`` table in ``docs/schema.md`` section 3.4.

Money is ``NUMERIC(12,2)`` and quantity is ``NUMERIC(12,3)``. Both map to Python
``Decimal``; neither is ever a ``float`` (``docs/schema.md`` section 7.2).

``current_stock`` is the opening balance only. Every later change goes through a
``StockMovement`` row, which is the immutable ledger.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    """A sellable product with pricing and stock levels."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2, asdecimal=True), nullable=False, default=Decimal("0")
    )
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2, asdecimal=True), nullable=False
    )
    current_stock: Mapped[Decimal] = mapped_column(
        Numeric(12, 3, asdecimal=True), nullable=False, default=Decimal("0")
    )
    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 3, asdecimal=True), nullable=False, default=Decimal("0")
    )
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

    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="products", lazy="selectin"
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement", back_populates="product", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"


from app.models.category import Category  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
