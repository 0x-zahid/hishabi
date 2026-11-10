"""Seed the three demo accounts used during the presentation.

Owner: Zahid. Idempotent: running it twice leaves exactly one account per
demo user and never duplicates or overwrites an existing account.

Run it with::

    python -m app.db.seed_demo_users

It creates one account per role so every permission tier can be demonstrated:

- ``owner``  - full control, including manual stock adjustments and deletes.
- ``staff``  - day-to-day operations: record stock movements, manage products.
- ``viewer`` - read-only access.

Passwords are never hardcoded in this file. Each one is read from an
environment variable, with a demo-only default so the script runs out of the
box::

    DEMO_OWNER_PASSWORD  (default: owner_pass123)
    DEMO_STAFF_PASSWORD  (default: staff_pass123)
    DEMO_VIEWER_PASSWORD (default: viewer_pass123)

Set them in the environment (or in ``.env``) to use different ones. The
plaintext is only ever used to build the bcrypt hash and to print the
credentials at the end of the run; it is never stored (PROJECT_RULES.md,
"Secrets and configuration").
"""

import os

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User

# The demo roles this script provisions. ``viewer`` is not seeded by
# ``app.db.seed_roles`` because the app itself never grants it; this script
# creates it on demand so the read-only tier can be demoed.
DEMO_USERS: list[tuple[str, str, str, str]] = [
    # (username, full_name, role_name, env var holding the password)
    ("owner", "Demo Owner", "owner", "DEMO_OWNER_PASSWORD"),
    ("staff", "Demo Staff", "staff", "DEMO_STAFF_PASSWORD"),
    ("viewer", "Demo Viewer", "viewer", "DEMO_VIEWER_PASSWORD"),
]

# Fallbacks used when the environment variable is not set.
DEFAULT_PASSWORDS: dict[str, str] = {
    "DEMO_OWNER_PASSWORD": "owner_pass123",
    "DEMO_STAFF_PASSWORD": "staff_pass123",
    "DEMO_VIEWER_PASSWORD": "viewer_pass123",
}


def _password_for(env_var: str) -> str:
    """Return the demo password from the environment, or its default.

    An environment variable that is set but empty is treated as unset, so an
    accidental ``DEMO_OWNER_PASSWORD=`` in a shell does not create an account
    that nobody can log into.
    """
    value = os.environ.get(env_var, "").strip()
    return value or DEFAULT_PASSWORDS[env_var]


def _ensure_role(db: Session, name: str) -> Role:
    """Return the role named ``name``, creating it when it is missing.

    The role is looked up rather than assumed, so the script also works
    against a database where ``app.db.seed_roles`` has already run.
    """
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role

    role = Role(name=name, description=f"{name} role")
    db.add(role)
    db.flush()
    return role


def seed_demo_users(db: Session) -> list[User]:
    """Create any missing demo account and return every demo user.

    An existing account is left exactly as it is: a password changed during the
    demo is not reset by a rerun, and the role already assigned is kept.
    """
    users: list[User] = []

    for username, full_name, role_name, env_var in DEMO_USERS:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            users.append(existing)
            continue

        role = _ensure_role(db, role_name)
        user = User(
            full_name=full_name,
            username=username,
            email=f"{username}@demo.hishabi",
            password_hash=hash_password(_password_for(env_var)),
            role_id=role.id,
            is_active=True,
        )
        db.add(user)
        users.append(user)

    db.commit()

    for user in users:
        db.refresh(user)

    return users


def main() -> None:
    """Seed the demo accounts and print the credentials for the demo."""
    db = SessionLocal()
    try:
        users = seed_demo_users(db)

        print("Demo accounts ready (role -> username):")
        for username, _full_name, role_name, _env_var in DEMO_USERS:
            print(f"  {role_name:<8} {username}")

        print("\nLogin credentials:")
        for username, _full_name, role_name, env_var in DEMO_USERS:
            print(f"  {username:<8} {role_name:<8} {_password_for(env_var)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
