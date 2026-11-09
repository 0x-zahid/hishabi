"""Request and response schemas for product categories.

Owner: Azaz (237). Field names follow the ``categories`` table in
``docs/schema.md`` section 3.3.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class CategoryCreate(BaseModel):
    """Body for creating a category."""

    model_config = ConfigDict(extra="forbid")

    name: CategoryName


class CategoryUpdate(BaseModel):
    """Body for renaming a category. ``name`` is the only editable column."""

    model_config = ConfigDict(extra="forbid")

    name: CategoryName


class CategoryOut(BaseModel):
    """Public representation of a category."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class CategoryListOut(BaseModel):
    """List of categories in the shared ``items`` / ``total`` shape."""

    items: list[CategoryOut]
    total: int


class CategoryMessageResponse(BaseModel):
    """Response returned upon category deletion."""

    message: str = "Category deleted successfully."
