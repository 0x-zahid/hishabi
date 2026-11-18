"""Payment model (a customer payment that settles part or all of a due).

Owner: Zahid. Maps to the ``payments`` table in ``docs/schema.md`` section 3.13.

A payment is an immutable record: it is never updated or deleted, and a
mistake is corrected with a new reversing entry (R19).

The customer's outstanding due is never stored on this table or on
``customers``. It is computed from the credit sales and the payments with
``app/services/dues_service.py`` (R16), so the two can never drift apart.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Payment(Base):
    """A payment received from a customer against their due."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sale_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    customer: Mapped["Customer"] = relationship("Customer", lazy="selectin")
    user: Mapped["User | None"] = relationship("User", lazy="selectin")
    sale: Mapped["Sale | None"] = relationship("Sale", back_populates="payments", lazy="raise")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} customer_id={self.customer_id} amount={self.amount}>"


from app.models.customer import Customer  # noqa: E402
from app.models.sale import Sale  # noqa: E402
from app.models.user import User  # noqa: E402
