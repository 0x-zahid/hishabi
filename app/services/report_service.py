"""Report calculations and queries.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md: all report queries live here, keeping routers thin.

Profit Rule:
Gross Profit = Total Revenue - Cost of Goods Sold (COGS).
Product.purchase_price is used as unit cost of goods sold.

Sales & Dues Isolation:
Zahid's sales/payments tables are not yet merged. The helper functions below
query sales from the database if the tables exist, or derive from existing
stock movements (movement_type='sale') and products, returning clean 0 values
when no sales exist.
"""

import re
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.customer import Customer
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.schemas.report import (
    CustomerDueItem,
    DailySalesReportOut,
    DailySummaryItem,
    DueReportOut,
    MonthlySalesReportOut,
    ProfitReportOut,
)

MONEY_PLACES = Decimal("0.01")


def _money(val: Decimal) -> Decimal:
    return val.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Sales & Profit Data Extraction Helper
# ---------------------------------------------------------------------------


def _get_sales_for_range(
    db: Session, start_dt: datetime, end_dt: datetime
) -> list[dict[str, Any]]:
    """Fetch sales lines within [start_dt, end_dt).

    If a dedicated 'sales' / 'sale_items' table exists, it queries it.
    Otherwise, it derives sales lines from stock_movements (type='sale') joined with Product.
    """
    # 1. Check if Zahid's Sale model / table is present
    if "sales" in Base.metadata.tables and "sale_items" in Base.metadata.tables:
        sales_table = Base.metadata.tables["sales"]
        items_table = Base.metadata.tables["sale_items"]
        query = (
            db.query(
                items_table.c.quantity,
                items_table.c.unit_price,
                Product.purchase_price,
                sales_table.c.payment_type,
            )
            .join(sales_table, items_table.c.sale_id == sales_table.c.id)
            .join(Product, items_table.c.product_id == Product.id)
            .filter(sales_table.c.created_at >= start_dt, sales_table.c.created_at < end_dt)
        )
        results = []
        for qty, u_price, p_price, pay_type in query.all():
            results.append({
                "quantity": Decimal(qty),
                "sale_price": Decimal(u_price),
                "purchase_price": Decimal(p_price),
                "payment_type": str(pay_type or "cash").lower(),
            })
        return results

    # 2. Fallback: derive sales from stock_movements (type='sale')
    movements = (
        db.query(StockMovement, Product)
        .join(Product, StockMovement.product_id == Product.id)
        .filter(
            StockMovement.movement_type == "sale",
            StockMovement.created_at >= start_dt,
            StockMovement.created_at < end_dt,
        )
        .all()
    )
    results = []
    for mov, prod in movements:
        results.append({
            "quantity": mov.quantity,
            "sale_price": prod.sale_price,
            "purchase_price": prod.purchase_price,
            "payment_type": "cash",  # Default if not stored in stock movement
        })
    return results


# ---------------------------------------------------------------------------
# 1. Daily Sales Report
# ---------------------------------------------------------------------------


def get_daily_sales_report(db: Session, target_date: date) -> DailySalesReportOut:
    """Calculate daily sales, profit, and cash vs credit split for one date."""
    start_dt = datetime.combine(target_date, time.min)
    end_dt = start_dt + timedelta(days=1)

    sales_lines = _get_sales_for_range(db, start_dt, end_dt)

    total_sales = Decimal("0.00")
    total_cogs = Decimal("0.00")
    cash_sales = Decimal("0.00")
    credit_sales = Decimal("0.00")

    for line in sales_lines:
        revenue = line["quantity"] * line["sale_price"]
        cogs = line["quantity"] * line["purchase_price"]

        total_sales += revenue
        total_cogs += cogs

        if line["payment_type"] == "credit":
            credit_sales += revenue
        else:
            cash_sales += revenue

    gross_profit = total_sales - total_cogs

    return DailySalesReportOut(
        date=target_date,
        sales_count=len(sales_lines),
        total_sales_amount=_money(total_sales),
        total_profit=_money(gross_profit),
        cash_sales_amount=_money(cash_sales),
        credit_sales_amount=_money(credit_sales),
    )


# ---------------------------------------------------------------------------
# 2. Monthly Sales Report
# ---------------------------------------------------------------------------


def get_monthly_sales_report(db: Session, year: int, month: int) -> MonthlySalesReportOut:
    """Calculate monthly sales, profit, and day-by-day breakdown."""
    _, num_days = monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    sales_lines = _get_sales_for_range(db, start_dt, end_dt)

    total_sales = Decimal("0.00")
    total_cogs = Decimal("0.00")
    cash_sales = Decimal("0.00")
    credit_sales = Decimal("0.00")

    # Group by day
    days_map: dict[date, dict[str, Any]] = {
        date(year, month, d): {
            "sales_count": 0,
            "total_sales_amount": Decimal("0.00"),
            "total_profit": Decimal("0.00"),
        }
        for d in range(1, num_days + 1)
    }

    for line in sales_lines:
        rev = line["quantity"] * line["sale_price"]
        cogs = line["quantity"] * line["purchase_price"]
        prof = rev - cogs

        total_sales += rev
        total_cogs += cogs
        if line["payment_type"] == "credit":
            credit_sales += rev
        else:
            cash_sales += rev

    # Query per day for breakdown
    for d in range(1, num_days + 1):
        cur_d = date(year, month, d)
        d_start = datetime.combine(cur_d, time.min)
        d_end = d_start + timedelta(days=1)
        d_lines = [l for l in sales_lines if d_start <= d_start < d_end]  # or from daily report
        d_rep = get_daily_sales_report(db, cur_d)
        days_map[cur_d] = {
            "sales_count": d_rep.sales_count,
            "total_sales_amount": d_rep.total_sales_amount,
            "total_profit": d_rep.total_profit,
        }

    daily_items = [
        DailySummaryItem(
            date=d,
            sales_count=v["sales_count"],
            total_sales_amount=v["total_sales_amount"],
            total_profit=v["total_profit"],
        )
        for d, v in sorted(days_map.items())
    ]

    return MonthlySalesReportOut(
        year=year,
        month=month,
        sales_count=len(sales_lines),
        total_sales_amount=_money(total_sales),
        total_profit=_money(total_sales - total_cogs),
        cash_sales_amount=_money(cash_sales),
        credit_sales_amount=_money(credit_sales),
        days=daily_items,
    )


# ---------------------------------------------------------------------------
# 3. Customer Due Report
# ---------------------------------------------------------------------------


def _extract_customer_due(cust: Customer) -> Decimal:
    """Extract due balance from note if present (e.g. '1000' or 'due: 1500')."""
    if not cust.note:
        return Decimal("0.00")
    m = re.search(r"\b\d+(\.\d{1,2})?\b", cust.note)
    if m:
        try:
            return Decimal(m.group(0))
        except Exception:
            return Decimal("0.00")
    return Decimal("0.00")


def get_due_report(db: Session) -> DueReportOut:
    """Return total outstanding customer dues and individual customer breakdown."""
    customers = db.query(Customer).order_by(Customer.name.asc()).all()

    items = []
    total_due = Decimal("0.00")

    for cust in customers:
        due_val = _extract_customer_due(cust)
        item = CustomerDueItem(
            customer_id=cust.id,
            customer_name=cust.name,
            phone=cust.phone,
            total_sales=_money(due_val),
            total_paid=Decimal("0.00"),
            current_due=_money(due_val),
        )
        items.append(item)
        total_due += due_val

    return DueReportOut(
        total_due_amount=_money(total_due),
        customer_count=len(customers),
        customers=items,
    )


# ---------------------------------------------------------------------------
# 4. Profit Report
# ---------------------------------------------------------------------------


def get_profit_report(db: Session, start_date: date, end_date: date) -> ProfitReportOut:
    """Calculate revenue, cost of goods sold, and gross profit over [start_date, end_date]."""
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    sales_lines = _get_sales_for_range(db, start_dt, end_dt)

    total_revenue = Decimal("0.00")
    total_cogs = Decimal("0.00")

    for line in sales_lines:
        revenue = line["quantity"] * line["sale_price"]
        cogs = line["quantity"] * line["purchase_price"]

        total_revenue += revenue
        total_cogs += cogs

    gross_profit = total_revenue - total_cogs

    return ProfitReportOut(
        start_date=start_date,
        end_date=end_date,
        total_revenue=_money(total_revenue),
        total_cogs=_money(total_cogs),
        gross_profit=_money(gross_profit),
    )
