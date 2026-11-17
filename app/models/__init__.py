"""SQLAlchemy ORM models for Hishabi.

Owner: Zahid. One model per file, named after the snake_case of the model.
Importing this package registers every table on ``Base.metadata``, which is
what Alembic's autogenerate compares against the live database.

Field names, column types, nullability and ON DELETE behaviour follow
``docs/schema.md`` section 3 and section 4 exactly.
"""

from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.product import Product
from app.models.role import Role
from app.models.stock_movement import StockMovement
from app.models.user import User

# Module 2 (Azaz): customers, suppliers and purchases.
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

__all__ = [
    "AuditLog",
    "Category",
    "Customer",
    "Product",
    "Purchase",
    "PurchaseItem",
    "Role",
    "StockMovement",
    "Supplier",
    "User",
]
