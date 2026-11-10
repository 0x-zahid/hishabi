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

__all__ = [
    "AuditLog",
    "Category",
    "Product",
    "Role",
    "StockMovement",
    "User",
]
