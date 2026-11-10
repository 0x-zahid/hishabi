"""Category model.

Owner: Zahid. Maps to the ``categories`` table in ``docs/schema.md`` section 3.3.

The name is unique. Deleting a category cascades to its products
(``docs/schema.md`` section 4).
"""

from datetime import datetime

from sqlalchemy import DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Category(Base):
    """A product category."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"


from app.models.product import Product  # noqa: E402
