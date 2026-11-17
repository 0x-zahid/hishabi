"""Request and response schemas for Owner Dashboard.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.stock import LowStockProductOut

MONEY_PLACES = Decimal("0.01")


def _money(val: Decimal | None) -> str:
    if val is None:
        return "0.00"
    return str(val.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


class RecentTransactionItem(BaseModel):
    """Recent business transaction item (sale, purchase, payment, stock adjustment)."""

    id: int
    transaction_type: str  # "sale", "purchase", "payment", "stock_movement"
    reference_name: str | None = None  # Customer name, Supplier name, or Product name
    amount: Decimal = Decimal("0.00")
    created_at: datetime

    @field_serializer("amount")
    def _serialize_amount(self, val: Decimal) -> str:
        return _money(val)


class DashboardSummaryOut(BaseModel):
    """Aggregated Owner Dashboard summary response."""

    # 1. Today's sales
    today_sales_amount: Decimal = Decimal("0.00")
    today_sales_count: int = 0

    # 2. Total customer dues
    total_customer_dues: Decimal = Decimal("0.00")

    # 3. Low-stock products
    low_stock_count: int = 0
    low_stock_products: list[LowStockProductOut] = Field(default_factory=list)

    # 4. 10 most recent transactions
    recent_transactions: list[RecentTransactionItem] = Field(default_factory=list)

    @field_serializer("today_sales_amount", "total_customer_dues")
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)
