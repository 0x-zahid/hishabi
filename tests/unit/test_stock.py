"""Unit tests for stock movements and low-stock reporting.

Owner: Zahid. Complies with PROJECT_RULES.md and docs/schema.md.

Tests cover:
- Recording a sale reduces the product's stock.
- Recording a purchase increases the product's stock.
- A return increases stock.
- A movement that would take stock below zero is rejected with 400.
- The stock_movements row is written with the correct balance_after.
- A rejected movement leaves no movement row and no stock change.
- Only an owner may post a manual adjustment.
- Staff and owners may post movements; other roles get 403.
- An unauthenticated request gets 401.
- Listing movements is newest first and can be filtered.
- The low-stock endpoint returns products at or below their threshold.
"""

from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.stock import router as stock_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.role import Role
from app.models.stock_movement import StockMovement
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with the auth and stock routers mounted."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(stock_router)

    @app.exception_handler(HTTPException)
    def http_exception_handler(request, exc):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _make_role(db: Session, name: str) -> Role:
    """Create a role with ``name`` if it does not exist yet."""
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name, description=f"{name} role")
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def _login(client: TestClient, db: Session, username: str, role_name: str | None) -> str:
    """Register a user with a role and return their access token."""
    user = User(
        full_name=f"User {username}",
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if role_name:
        role = _make_role(db, role_name)
        user.role_id = role.id
        db.commit()

    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _make_product(db: Session, stock: str = "100.000", threshold: str = "10.000") -> Product:
    """Create a product with the given opening stock."""
    product = Product(
        category_id=None,
        name="চাল",
        unit="kg",
        purchase_price=Decimal("55.00"),
        sale_price=Decimal("60.00"),
        current_stock=Decimal(stock),
        low_stock_threshold=Decimal(threshold),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _stock_of(db: Session, product_id: int) -> Decimal:
    """Return the current stock of a product straight from the database."""
    db.expire_all()
    product = db.query(Product).filter(Product.id == product_id).first()
    return product.current_stock


# ---------------------------------------------------------------------------
# 1. Sale reduces stock
# ---------------------------------------------------------------------------


def test_recording_a_sale_reduces_stock(
    client: TestClient, test_db_session: Session
):
    """A sale decreases the product's stock."""
    token = _login(client, test_db_session, "staff_sale", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "30.000",
            "note": "Sold to customer",
        },
    )
    assert response.status_code == 201, response.text
    assert _stock_of(test_db_session, product.id) == Decimal("70.000")


def test_recording_a_purchase_increases_stock(
    client: TestClient, test_db_session: Session
):
    """A purchase increases the product's stock."""
    token = _login(client, test_db_session, "staff_purchase", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "purchase",
            "quantity": "50.000",
            "note": "Bought from supplier",
        },
    )
    assert response.status_code == 201, response.text
    assert _stock_of(test_db_session, product.id) == Decimal("150.000")


def test_recording_a_return_increases_stock(
    client: TestClient, test_db_session: Session
):
    """A return brings goods back into stock."""
    token = _login(client, test_db_session, "staff_return", "staff")
    product = _make_product(test_db_session, stock="20.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "return",
            "quantity": "5.000",
        },
    )
    assert response.status_code == 201, response.text
    assert _stock_of(test_db_session, product.id) == Decimal("25.000")


# ---------------------------------------------------------------------------
# 2. Negative stock is rejected
# ---------------------------------------------------------------------------


def test_negative_stock_is_rejected_with_400(
    client: TestClient, test_db_session: Session
):
    """A sale larger than the stock on hand is rejected."""
    token = _login(client, test_db_session, "staff_oversell", "staff")
    product = _make_product(test_db_session, stock="10.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "25.000",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"


def test_rejected_movement_does_not_change_stock(
    client: TestClient, test_db_session: Session
):
    """A rejected movement leaves the stock untouched and writes no row."""
    token = _login(client, test_db_session, "staff_rollback", "staff")
    product = _make_product(test_db_session, stock="10.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "999.000",
        },
    )
    assert response.status_code == 400

    assert _stock_of(test_db_session, product.id) == Decimal("10.000")
    movements = test_db_session.query(StockMovement).filter(
        StockMovement.product_id == product.id
    ).all()
    assert movements == []


def test_movement_on_missing_product_returns_404(
    client: TestClient, test_db_session: Session
):
    """A movement for a product that does not exist is a 404."""
    token = _login(client, test_db_session, "staff_noproduct", "staff")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": 9999,
            "movement_type": "sale",
            "quantity": "1.000",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 3. The movement row and balance_after
# ---------------------------------------------------------------------------


def test_stock_movements_row_created_with_correct_balance_after(
    client: TestClient, test_db_session: Session
):
    """The movement row records the stock level after the movement."""
    token = _login(client, test_db_session, "staff_ledger", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "40.000",
            "note": "Wholesale order",
        },
    )
    assert response.status_code == 201, response.text

    movement = test_db_session.query(StockMovement).filter(
        StockMovement.product_id == product.id
    ).one()
    assert movement.movement_type == "sale"
    assert movement.quantity == Decimal("40.000")
    assert movement.balance_after == Decimal("60.000")
    assert movement.note == "Wholesale order"
    assert movement.user_id is not None


def test_balance_after_accumulates_across_movements(
    client: TestClient, test_db_session: Session
):
    """Each row's balance_after reflects the running stock level."""
    token = _login(client, test_db_session, "staff_running", "staff")
    product = _make_product(test_db_session, stock="100.000")

    for quantity in ("10.000", "5.000", "2.500"):
        response = client.post(
            "/api/v1/stock-movements",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "product_id": product.id,
                "movement_type": "sale",
                "quantity": quantity,
            },
        )
        assert response.status_code == 201, response.text

    balances = [
        m.balance_after
        for m in test_db_session.query(StockMovement)
        .filter(StockMovement.product_id == product.id)
        .order_by(StockMovement.id.asc())
        .all()
    ]
    assert balances == [Decimal("90.000"), Decimal("85.000"), Decimal("82.500")]


def test_response_contains_the_movement(
    client: TestClient, test_db_session: Session
):
    """The response body carries the new movement."""
    token = _login(client, test_db_session, "staff_response", "staff")
    product = _make_product(test_db_session, stock="50.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "purchase",
            "quantity": "12.000",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["product_id"] == product.id
    assert data["movement_type"] == "purchase"
    assert data["quantity"] == "12.000"
    assert data["balance_after"] == "62.000"


def test_audit_row_is_written(
    client: TestClient, test_db_session: Session
):
    """Recording a movement writes an audit row."""
    token = _login(client, test_db_session, "staff_audit", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "5.000",
        },
    )
    assert response.status_code == 201, response.text

    audit = test_db_session.query(AuditLog).filter(
        AuditLog.action == "stock_movement"
    ).one()
    assert audit.new_value["current_stock"] == "95.000"
    assert audit.old_value["current_stock"] == "100.000"


# ---------------------------------------------------------------------------
# 4. Adjustments are owner-only
# ---------------------------------------------------------------------------


def test_owner_can_post_an_adjustment(
    client: TestClient, test_db_session: Session
):
    """An owner may post a manual adjustment, including a negative one."""
    token = _login(client, test_db_session, "owner_adj", "owner")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "adjustment",
            "quantity": "-10.000",
            "note": "Damaged in transit",
        },
    )
    assert response.status_code == 201, response.text
    assert _stock_of(test_db_session, product.id) == Decimal("90.000")


def test_staff_cannot_post_an_adjustment(
    client: TestClient, test_db_session: Session
):
    """A staff user is forbidden from posting a manual adjustment."""
    token = _login(client, test_db_session, "staff_adj", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "adjustment",
            "quantity": "-10.000",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert _stock_of(test_db_session, product.id) == Decimal("100.000")


def test_viewer_cannot_record_a_movement(
    client: TestClient, test_db_session: Session
):
    """A viewer is forbidden from recording a stock movement."""
    token = _login(client, test_db_session, "viewer_stock", "viewer")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "1.000",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_user_without_a_role_cannot_record_a_movement(
    client: TestClient, test_db_session: Session
):
    """A user with no role is forbidden from recording a movement."""
    token = _login(client, test_db_session, "roleless_stock", None)
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "1.000",
        },
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 5. Authentication and validation
# ---------------------------------------------------------------------------


def test_no_token_returns_401(client: TestClient, test_db_session: Session):
    """Recording a movement without a token is rejected."""
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "1.000",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_movement_type_returns_422(
    client: TestClient, test_db_session: Session
):
    """An unknown movement type is rejected by the schema."""
    token = _login(client, test_db_session, "staff_badtype", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "steal",
            "quantity": "1.000",
        },
    )
    assert response.status_code == 422


def test_negative_quantity_on_a_sale_returns_422(
    client: TestClient, test_db_session: Session
):
    """Only an adjustment may carry a negative quantity."""
    token = _login(client, test_db_session, "staff_negsale", "staff")
    product = _make_product(test_db_session, stock="100.000")

    response = client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product.id,
            "movement_type": "sale",
            "quantity": "-5.000",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6. Listing movements
# ---------------------------------------------------------------------------


def test_list_movements_returns_newest_first(
    client: TestClient, test_db_session: Session
):
    """The listing is ordered newest first."""
    token = _login(client, test_db_session, "staff_list", "staff")
    product = _make_product(test_db_session, stock="100.000")

    for quantity in ("1.000", "2.000", "3.000"):
        client.post(
            "/api/v1/stock-movements",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "product_id": product.id,
                "movement_type": "sale",
                "quantity": quantity,
            },
        )

    response = client.get(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    quantities = [item["quantity"] for item in data["items"]]
    assert quantities == ["3.000", "2.000", "1.000"]


def test_list_movements_filters_by_product_and_type(
    client: TestClient, test_db_session: Session
):
    """The listing can be filtered by product and by movement type."""
    token = _login(client, test_db_session, "staff_filter", "staff")
    product = _make_product(test_db_session, stock="100.000")
    other = _make_product(test_db_session, stock="100.000")
    other.name = "ডাল"

    client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product.id, "movement_type": "sale", "quantity": "1.000"},
    )
    client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product.id, "movement_type": "purchase", "quantity": "2.000"},
    )
    client.post(
        "/api/v1/stock-movements",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": other.id, "movement_type": "sale", "quantity": "3.000"},
    )

    response = client.get(
        f"/api/v1/stock-movements?product_id={product.id}&movement_type=sale",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["product_id"] == product.id
    assert data["items"][0]["movement_type"] == "sale"


def test_list_movements_requires_authentication(client: TestClient):
    """The listing is not public."""
    response = client.get("/api/v1/stock-movements")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 7. Low stock
# ---------------------------------------------------------------------------


def test_low_stock_lists_products_at_threshold(
    client: TestClient, test_db_session: Session
):
    """Products at or below the threshold are listed."""
    token = _login(client, test_db_session, "staff_low", "staff")

    low = _make_product(test_db_session, stock="5.000", threshold="10.000")
    low.name = "Low Stock Item"
    exactly = _make_product(test_db_session, stock="10.000", threshold="10.000")
    exactly.name = "Exactly At Threshold"
    plenty = _make_product(test_db_session, stock="50.000", threshold="10.000")
    plenty.name = "Plenty In Stock"
    test_db_session.commit()

    response = client.get(
        "/api/v1/low-stock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    names = [item["name"] for item in data["items"]]
    assert "Low Stock Item" in names
    assert "Exactly At Threshold" in names
    assert "Plenty In Stock" not in names
    assert data["total"] == len(data["items"])


def test_low_stock_excludes_inactive_products(
    client: TestClient, test_db_session: Session
):
    """A discontinued product is not reported as low stock."""
    token = _login(client, test_db_session, "staff_inactive", "staff")

    discontinued = _make_product(test_db_session, stock="1.000", threshold="10.000")
    discontinued.name = "Discontinued"
    discontinued.is_active = False
    test_db_session.commit()

    response = client.get(
        "/api/v1/low-stock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "Discontinued" not in names


def test_low_stock_requires_authentication(client: TestClient):
    """The low-stock endpoint is not public."""
    response = client.get("/api/v1/low-stock")
    assert response.status_code == 401
