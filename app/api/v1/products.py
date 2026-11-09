"""Product management endpoints: CRUD for products.

Owner: Azaz (Student ID: 237).
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import Base, get_db
from app.schemas.product import (
    ProductCreate,
    ProductListOut,
    ProductMessageResponse,
    ProductOut,
    ProductUpdate,
)

# ---------------------------------------------------------------------------
# Database Models (uses Zahid's models if available, or schema.md §3.4 fallback)
# ---------------------------------------------------------------------------

try:
    from app.models.category import Category
except ImportError:
    from app.api.v1.categories import Category

try:
    from app.models.role import Role
    from app.models.user import User
except ImportError:
    from app.api.v1.auth import Role, User

try:
    from app.models.product import Product
except ImportError:
    from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, Numeric, String, func
    from sqlalchemy.orm import Mapped, mapped_column

    class Product(Base):  # type: ignore[no-redef]
        __tablename__ = "products"

        id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
        category_id: Mapped[int | None] = mapped_column(
            Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True, index=True
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
            DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
        )


# ---------------------------------------------------------------------------
# Current User Dependency (uses Zahid's deps if available, or fallback from users.py)
# ---------------------------------------------------------------------------

try:
    from app.api.deps import get_current_user
except ImportError:
    from app.api.v1.users import get_current_user


# ---------------------------------------------------------------------------
# Helper functions for Error & Role Checking
# ---------------------------------------------------------------------------


def _api_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _get_role_name(user: User, db: Session) -> str | None:
    """Return lowercase role name for user, or None."""
    if not user.role_id:
        return None
    role = db.query(Role).filter(Role.id == user.role_id).first()
    return role.name.lower() if role else None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductOut,
    summary="Create a new product",
)
def create_product(
    body: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new product with pricing, unit, and quantity details.

    Staff and Owners can create products.
    """
    role_name = _get_role_name(current_user, db)
    if role_name and role_name not in ["owner", "admin", "staff"]:
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Staff or owner permissions required to create products.",
        )

    # Validate category exists if provided
    if body.category_id is not None:
        cat = db.query(Category).filter(Category.id == body.category_id).first()
        if not cat:
            return _api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_CATEGORY",
                "Category not found.",
            )

    product = Product(
        category_id=body.category_id,
        name=body.name,
        unit=body.unit,
        purchase_price=body.purchase_price,
        sale_price=body.sale_price,
        current_stock=body.current_stock,
        low_stock_threshold=body.low_stock_threshold,
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return product


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ProductListOut,
    summary="List all products",
)
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    category_id: int | None = Query(None, gt=0),
    is_active: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List products with pagination, name search, and category filtering."""
    query = db.query(Product).filter(Product.is_active == is_active)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if category_id:
        query = query.filter(Product.category_id == category_id)

    total = query.count()
    items = query.order_by(Product.id.asc()).offset(skip).limit(limit).all()

    return ProductListOut(items=items, total=total)


@router.get(
    "/{product_id}",
    status_code=status.HTTP_200_OK,
    response_model=ProductOut,
    summary="Get product by ID",
)
def get_product_by_id(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details of a single product by ID."""
    product = db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not product:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Product not found.",
        )
    return product


@router.put(
    "/{product_id}",
    status_code=status.HTTP_200_OK,
    response_model=ProductOut,
    summary="Update product by ID",
)
@router.patch(
    "/{product_id}",
    status_code=status.HTTP_200_OK,
    response_model=ProductOut,
    include_in_schema=False,
)
def update_product(
    product_id: int,
    body: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update product details. Staff and Owners can edit products."""
    role_name = _get_role_name(current_user, db)
    if role_name and role_name not in ["owner", "admin", "staff"]:
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Staff or owner permissions required to edit products.",
        )

    product = db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not product:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Product not found.",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Validate category exists if category_id is updated
    if "category_id" in update_data and update_data["category_id"] is not None:
        cat = db.query(Category).filter(Category.id == update_data["category_id"]).first()
        if not cat:
            return _api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_CATEGORY",
                "Category not found.",
            )

    for field, value in update_data.items():
        setattr(product, field, value)

    product.updated_at = datetime.now()
    db.commit()
    db.refresh(product)

    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_200_OK,
    response_model=ProductMessageResponse,
    summary="Delete product by ID",
)
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a product. Only Owner can delete products."""
    role_name = _get_role_name(current_user, db)
    if role_name != "owner":
        return _api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Only an owner can delete products.",
        )

    product = db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not product:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Product not found.",
        )

    # Soft delete per PROJECT_RULES.md
    product.is_active = False
    product.updated_at = datetime.now()
    db.commit()

    return ProductMessageResponse(message="Product deleted successfully.")

