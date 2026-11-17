"""Request and response schemas for business reports.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md and docs/schema.md.

All monetary amounts are Decimal serialized as JSON strings with 2 decimal places.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

MONEY_PLACES = Decimal("0.01")


def _money(val: Decimal | None) -> str:
    if val is None:
        return "0.00"
    return str(val.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Daily Sales Report
# ---------------------------------------------------------------------------


class DailySalesReportOut(BaseModel):
    """Daily sales metrics for a single date."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    sales_count: int
    total_sales_amount: Decimal
    total_profit: Decimal
    cash_sales_amount: Decimal
    credit_sales_amount: Decimal

    @field_serializer(
        "total_sales_amount",
        "total_profit",
        "cash_sales_amount",
        "credit_sales_amount",
    )
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


# ---------------------------------------------------------------------------
# Monthly Sales Report
# ---------------------------------------------------------------------------


class DailySummaryItem(BaseModel):
    """Day-by-day summary item inside a monthly report."""

    date: date
    sales_count: int
    total_sales_amount: Decimal
    total_profit: Decimal

    @field_serializer("total_sales_amount", "total_profit")
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


class MonthlySalesReportOut(BaseModel):
    """Monthly sales metrics aggregated across an entire month."""

    year: int
    month: int
    sales_count: int
    total_sales_amount: Decimal
    total_profit: Decimal
    cash_sales_amount: Decimal
    credit_sales_amount: Decimal
    days: list[DailySummaryItem] = Field(default_factory=list)

    @field_serializer(
        "total_sales_amount",
        "total_profit",
        "cash_sales_amount",
        "credit_sales_amount",
    )
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


# ---------------------------------------------------------------------------
# Customer Due Report
# ---------------------------------------------------------------------------


class CustomerDueItem(BaseModel):
    """Individual customer due breakdown item."""

    customer_id: int
    customer_name: str
    phone: str | None = None
    total_sales: Decimal = Decimal("0.00")
    total_paid: Decimal = Decimal("0.00")
    current_due: Decimal = Decimal("0.00")

    @field_serializer("total_sales", "total_paid", "current_due")
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


class DueReportOut(BaseModel):
    """Overall customer dues report."""

    total_due_amount: Decimal
    customer_count: int
    customers: list[CustomerDueItem] = Field(default_factory=list)

    @field_serializer("total_due_amount")
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


# ---------------------------------------------------------------------------
# Profit Report
# ---------------------------------------------------------------------------


class ProfitReportOut(BaseModel):
    """Profit metrics over a given date range."""

    start_date: date
    end_date: date
    total_revenue: Decimal
    total_cogs: Decimal  # Cost of Goods Sold
    gross_profit: Decimal

    @field_serializer("total_revenue", "total_cogs", "gross_profit")
    def _serialize_money(self, val: Decimal) -> str:
        return _money(val)


# ---------------------------------------------------------------------------
# Export Query Params
# ---------------------------------------------------------------------------

ReportType = Literal["daily", "monthly", "dues", "profit"]
ExportFormat = Literal["pdf", "xlsx"]
