"""Dashboard summary queries.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md: all dashboard queries live here.

Four Sections:
1. Today's total sales amount and number of sales.
2. Total outstanding customer dues.
3. Count of low-stock products and the list of those products with current stock and threshold.
4. The 10 most recent transactions with id, type, name, amount, and timestamp.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.stock_movement import StockMovement
from app.schemas.dashboard import DashboardSummaryOut, RecentTransactionItem
from app.schemas.stock import LowStockProductOut
from app.services import report_service


def get_dashboard_summary(db: Session) -> DashboardSummaryOut:
    """Aggregate dashboard metrics in one call."""
    today = date.today()

    # 1. Today's sales
    daily_rep = report_service.get_daily_sales_report(db, today)
    today_sales_amt = daily_rep.total_sales_amount
    today_sales_cnt = daily_rep.sales_count

    # 2. Total customer dues
    due_rep = report_service.get_due_report(db)
    total_dues = due_rep.total_due_amount

    # 3. Low-stock products (reusing official threshold rule)
    low_stock_rows = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            Product.current_stock <= Product.low_stock_threshold,
        )
        .order_by(Product.name.asc())
        .all()
    )
    low_stock_items = [
        LowStockProductOut.model_validate(p) for p in low_stock_rows
    ]

    # 4. 10 most recent transactions
    # Fetch recent purchases
    recent_purchases = (
        db.query(Purchase)
        .order_by(Purchase.created_at.desc(), Purchase.id.desc())
        .limit(10)
        .all()
    )
    # Fetch recent stock movements
    recent_movements = (
        db.query(StockMovement, Product.name)
        .join(Product, StockMovement.product_id == Product.id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(10)
        .all()
    )

    transactions = []
    for pur in recent_purchases:
        supplier_name = pur.supplier.name if pur.supplier else None
        transactions.append(
            RecentTransactionItem(
                id=pur.id,
                transaction_type="purchase",
                reference_name=supplier_name,
                amount=pur.total_amount,
                created_at=pur.created_at,
            )
        )

    for mov, prod_name in recent_movements:
        # Ignore purchase stock movements to avoid duplicating the purchase record
        if mov.reference_type == "purchase":
            continue
        transactions.append(
            RecentTransactionItem(
                id=mov.id,
                transaction_type=f"stock_{mov.movement_type or 'movement'}",
                reference_name=prod_name,
                amount=mov.quantity,
                created_at=mov.created_at,
            )
        )

    # Sort combined transactions newest first, take top 10
    transactions.sort(key=lambda t: t.created_at, reverse=True)
    top_10 = transactions[:10]

    return DashboardSummaryOut(
        today_sales_amount=today_sales_amt,
        today_sales_count=today_sales_cnt,
        total_customer_dues=total_dues,
        low_stock_count=len(low_stock_items),
        low_stock_products=low_stock_items,
        recent_transactions=top_10,
    )
