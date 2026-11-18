"""Sale model (header of a sale to a customer or a walk-in buyer).

Owner: Zahid. Maps to the ``sales`` table in ``docs/schema.md`` section 3.11.

A sale is an immutable financial record: it is never updated or deleted, and a
mistake is corrected with a reversing entry (R19). The product lines live in
``sale_items``; this table holds the money summary.

``total_amount`` is ``NUMERIC(12,2)`` and always equals the sum of the
``line_total`` of its items. The server computes it; the client may only
cross-check it.

``due_amount`` is the part of the sale that was put on account. A customer's
outstanding due is never stored on any row: it is computed from the sales and
payments tables by ``app/services/dues_service.py`` so that there is exactly one
source of truth (R16).
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


class Sale(Base):
    """A sale of one or more products, paid in cash or on credit."""

    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_sales_total_amount_non_negative"),
        CheckConstraint("paid_amount >= 0", name="ck_sales_paid_amount_non_negative"),
        CheckConstraint("due_amount >= 0", name="ck_sales_due_amount_non_negative"),
        CheckConstraint(
            "payment_type IN ('cash','credit')",
            name="ck_sales_payment_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2, asdecimal=True), nullable=False, default=Decimal("0")
    )
    due_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2, asdecimal=True), nullable=False, default=Decimal("0")
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    customer: Mapped["Customer | None"] = relationship("Customer", lazy="selectin")
    user: Mapped["User | None"] = relationship("User", lazy="selectin")
    items: Mapped[list["SaleItem"]] = relationship(
        "SaleItem",
        back_populates="sale",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="SaleItem.id",
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="sale",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Sale id={self.id} customer_id={self.customer_id} "
            f"payment_type={self.payment_type!r} total_amount={self.total_amount}>"
        )


from app.models.customer import Customer  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.sale_item import SaleItem  # noqa: E402
from app.models.user import User  # noqa: E402
