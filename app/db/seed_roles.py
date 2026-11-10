"""Seed the ``roles`` table.

Owner: Zahid. Idempotent: running it twice leaves exactly one row per role and
never duplicates or overwrites an existing role.

Run it with::

    python -m app.db.seed_roles

The roles seeded here are the ones the API checks against:

- ``owner``  - full control, including manual stock adjustments and deletes.
- ``admin``  - administrative access to products and categories.
- ``staff``  - day-to-day operations: record stock movements, manage products.

``viewer`` is intentionally not seeded; it exists in the permission checks so
that a read-only account is rejected, but it is not a role the app grants.
"""

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.role import Role

ROLES: list[tuple[str, str]] = [
    ("owner", "Full control, including deletions and manual stock adjustments"),
    ("admin", "Administrative access to products, categories and users"),
    ("staff", "Day-to-day operations, including recording stock movements"),
]


def seed_roles(db: Session) -> list[Role]:
    """Insert any missing role and return every role.

    An existing role is left exactly as it is, so a renamed description in the
    database is not overwritten by a rerun.
    """
    created: list[Role] = []

    for name, description in ROLES:
        existing = db.query(Role).filter(Role.name == name).first()
        if existing:
            continue
        role = Role(name=name, description=description)
        db.add(role)
        created.append(role)

    db.commit()

    for role in created:
        db.refresh(role)

    return created


def main() -> None:
    """Seed the roles table and report what happened."""
    db = SessionLocal()
    try:
        created = seed_roles(db)
        if created:
            print("Created roles: " + ", ".join(role.name for role in created))
        else:
            print("All roles already present, nothing to do.")

        total = db.query(Role).count()
        print(f"Roles in table ({total}):")
        for role in db.query(Role).order_by(Role.id).all():
            print(f"  {role.id}  {role.name:<8} {role.description or ''}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
