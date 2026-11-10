"""Role model.

Owner: Zahid. Maps to the ``roles`` table in ``docs/schema.md`` section 3.1.

A role is a named access level (``owner``, ``staff``, ``viewer``, ``admin``).
The name is stored lowercase and is unique.
"""

from sqlalchemy import Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Role(Base):
    """An access role that can be assigned to a user."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"
