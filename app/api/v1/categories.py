"""Category management endpoints: CRUD for product categories.

Owner: Azaz (Student ID: 237).
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import Base, get_db
from app.schemas.category import (
    CategoryCreate,
    CategoryListOut,
    CategoryMessageResponse,
    CategoryOut,
    CategoryUpdate,
)

# ---------------------------------------------------------------------------
# Category Model (uses Zahid's model if available, or schema.md §3.3 definition)
# ---------------------------------------------------------------------------

try:
    from app.models.category import Category
except ImportError:
    from sqlalchemy import DateTime, Identity, Integer, String, func
    from sqlalchemy.orm import Mapped, mapped_column

    class Category(Base):  # type: ignore[no-redef]
        __tablename__ = "categories"

        id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
        name: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=False), server_default=func.now(), nullable=False
        )


# ---------------------------------------------------------------------------
# Current User Dependency (uses Zahid's deps if available, or fallback from users.py)
# ---------------------------------------------------------------------------

try:
    from app.api.deps import get_current_user
except ImportError:
    from app.api.v1.users import get_current_user


# ---------------------------------------------------------------------------
# Helper to produce standard API error responses per PROJECT_RULES.md
# ---------------------------------------------------------------------------


def _api_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CategoryOut,
    summary="Create a new category",
)
def create_category(
    body: CategoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a category with a unique name."""
    existing = db.query(Category).filter(Category.name == body.name).first()
    if existing:
        return _api_error(
            status.HTTP_409_CONFLICT,
            "CATEGORY_EXISTS",
            "A category with this name already exists.",
        )

    category = Category(name=body.name)
    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=CategoryListOut,
    summary="List all categories",
)
def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=80),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List categories with optional search filtering and pagination."""
    query = db.query(Category)
    if search:
        query = query.filter(Category.name.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(Category.id.asc()).offset(skip).limit(limit).all()

    return CategoryListOut(items=items, total=total)


@router.get(
    "/{category_id}",
    status_code=status.HTTP_200_OK,
    response_model=CategoryOut,
    summary="Get category by ID",
)
def get_category_by_id(
    category_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve category details by ID."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Category not found.",
        )
    return category


@router.put(
    "/{category_id}",
    status_code=status.HTTP_200_OK,
    response_model=CategoryOut,
    summary="Update category by ID",
)
@router.patch(
    "/{category_id}",
    status_code=status.HTTP_200_OK,
    response_model=CategoryOut,
    include_in_schema=False,
)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update category name. Name must remain unique."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Category not found.",
        )

    # Check uniqueness if name changed
    if body.name != category.name:
        existing = (
            db.query(Category)
            .filter(Category.name == body.name, Category.id != category_id)
            .first()
        )
        if existing:
            return _api_error(
                status.HTTP_409_CONFLICT,
                "CATEGORY_EXISTS",
                "A category with this name already exists.",
            )
        category.name = body.name

    db.commit()
    db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_200_OK,
    response_model=CategoryMessageResponse,
    summary="Delete category by ID",
)
def delete_category(
    category_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete category by ID."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return _api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Category not found.",
        )

    db.delete(category)
    db.commit()

    return CategoryMessageResponse(message="Category deleted successfully.")

