"""Request and response schemas for users and the user profile.

Owner: Azaz (237). Field names follow the ``users`` table in ``docs/schema.md``
section 3.2. ``password_hash`` is never part of any response schema.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.auth import Email, FullName, Password


class UserOut(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str | None
    role_id: int | None
    is_active: bool
    created_at: datetime


class UserListOut(BaseModel):
    """List of users in the shared ``items`` / ``total`` shape."""

    items: list[UserOut]
    total: int


class UserProfileUpdate(BaseModel):
    """Fields a user may change on their own profile.

    ``role_id``, ``is_active`` and ``username`` are rejected so a user cannot
    promote or re-identify themselves.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: FullName | None = None
    email: Email | None = None

    @model_validator(mode="after")
    def _full_name_not_null(self) -> "UserProfileUpdate":
        """``full_name`` is NOT NULL in the database, so an explicit null is invalid."""
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null.")
        return self


class PasswordChange(BaseModel):
    """Body for changing the current user's password."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[str, StringConstraints(min_length=1)]
    new_password: Password

    @model_validator(mode="after")
    def _new_differs_from_current(self) -> "PasswordChange":
        if self.new_password == self.current_password:
            raise ValueError("New password must be different from the current password.")
        return self


class UserAdminUpdate(BaseModel):
    """Fields an admin may change on another user: role and active status."""

    model_config = ConfigDict(extra="forbid")

    role_id: Annotated[int, Field(gt=0)] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _is_active_not_null(self) -> "UserAdminUpdate":
        """``is_active`` is NOT NULL in the database; ``role_id`` may be cleared."""
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active cannot be null.")
        return self


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
