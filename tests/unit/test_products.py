"""Unit tests for products and categories: schemas, CRUD, permissions, pagination, search, and filtering.

Owner: Azaz (Student ID: 237).
Complies with PROJECT_RULES.md and docs/schema.md.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.auth import Role, User, router as auth_router
from app.api.v1.categories import Category, router as categories_router
from app.api.v1.products import Product, router as products_router
from app.core.database import get_db
from app.schemas.category import (
    CategoryCreate,
    CategoryListOut,
    CategoryOut,
    CategoryUpdate,
)
from app.schemas.product import (
    ProductCreate,
    ProductListOut,
    ProductOut,
    ProductUpdate,
)

# ---------------------------------------------------------------------------
# 1. Schema Validation Tests
# ---------------------------------------------------------------------------


def _create(**overrides):
    data = {"name": "চাল", "unit": "kg", "sale_price": "60.00"}
    data.update(overrides)
    return ProductCreate(**data)


def test_product_create_defaults_and_decimal_types():
    body = _create()
    assert body.category_id is None
    assert body.purchase_price == Decimal("0")
    assert body.current_stock == Decimal("0")
    assert isinstance(body.sale_price, Decimal)


def test_product_create_accepts_fractional_stock():
    assert _create(current_stock="12.345").current_stock == Decimal("12.345")


@pytest.mark.parametrize(
    "field, value",
    [
        ("sale_price", "0"),
        ("sale_price", "-1"),
        ("purchase_price", "-0.01"),
        ("sale_price", "1.234"),
        ("sale_price", "12345678901.00"),
        ("current_stock", "1.2345"),
        ("low_stock_threshold", "-1"),
        ("name", ""),
        ("name", "a" * 121),
        ("unit", "a" * 21),
        ("category_id", 0),
    ],
)
def test_product_create_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _create(**{field: value})


def test_product_create_requires_name_unit_sale_price():
    with pytest.raises(ValidationError):
        ProductCreate(name="চাল", unit="kg")


def test_product_update_cannot_change_current_stock():
    with pytest.raises(ValidationError):
        ProductUpdate(current_stock="5")


def test_product_update_only_sent_fields():
    assert ProductUpdate(sale_price="65.50").model_dump(exclude_unset=True) == {
        "sale_price": Decimal("65.50")
    }


def test_product_update_allows_clearing_category_only():
    assert ProductUpdate(category_id=None).model_dump(exclude_unset=True) == {"category_id": None}
    for field in [
        "name",
        "unit",
        "purchase_price",
        "sale_price",
        "low_stock_threshold",
        "is_active",
    ]:
        with pytest.raises(ValidationError):
            ProductUpdate(**{field: None})


def _orm_product():
    return SimpleNamespace(
        id=1,
        category_id=2,
        name="চাল",
        unit="kg",
        purchase_price=Decimal("55"),
        sale_price=Decimal("60.005"),
        current_stock=Decimal("50"),
        low_stock_threshold=Decimal("5.5"),
        is_active=True,
        created_at=datetime(2026, 11, 10),
        updated_at=datetime(2026, 11, 10),
    )


def test_product_out_serialises_decimals_as_strings():
    data = ProductOut.model_validate(_orm_product()).model_dump(mode="json")
    assert data["purchase_price"] == "55.00"
    assert data["sale_price"] == "60.01"
    assert data["current_stock"] == "50.000"
    assert data["low_stock_threshold"] == "5.500"
    assert data["name"] == "চাল"


def test_product_list_shape():
    item = ProductOut.model_validate(_orm_product())
    data = ProductListOut(items=[item], total=1).model_dump(mode="json")
    assert set(data) == {"items", "total"}
    assert data["items"][0]["sale_price"] == "60.01"


def test_category_create_strips_and_accepts_bangla():
    assert CategoryCreate(name="  মুদি  ").name == "মুদি"


@pytest.mark.parametrize("name", ["", "   ", "a" * 81])
def test_category_name_rejects_empty_or_too_long(name):
    with pytest.raises(ValidationError):
        CategoryCreate(name=name)
    with pytest.raises(ValidationError):
        CategoryUpdate(name=name)


def test_category_create_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CategoryCreate(name="Rice", id=5)


def test_category_list_shape():
    item = CategoryOut.model_validate(
        SimpleNamespace(id=1, name="Rice", created_at=datetime(2026, 11, 10))
    )
    data = CategoryListOut(items=[item], total=1).model_dump()
    assert set(data) == {"items", "total"}
    assert data["total"] == 1


# ---------------------------------------------------------------------------
# 2. Integration Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db_session: Session):
    """FastAPI TestClient with all routers and error formatting."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(categories_router)
    app.include_router(products_router)

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


def _create_user_with_role(
    client: TestClient, db: Session, username: str, role_name: str | None = None
) -> str:
    """Helper to create a user and assign a specific role (owner, staff, etc.)."""
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"User {username}",
            "username": username,
            "email": f"{username}@test.com",
            "password": "Password123",
        },
    )

    if role_name:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name, description=f"{role_name} role")
            db.add(role)
            db.commit()
            db.refresh(role)

        user = db.query(User).filter(User.username == username).first()
        user.role_id = role.id
        db.commit()

    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# 3. Category CRUD Tests
# ---------------------------------------------------------------------------


def test_endpoint_create_category_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user")
    response = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "চাল ও ডাল"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "চাল ও ডাল"


def test_endpoint_create_category_duplicate_name(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user2")
    client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Beverages"},
    )
    res2 = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Beverages"},
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CATEGORY_EXISTS"


def test_endpoint_create_category_unauthorized(client: TestClient):
    response = client.post("/api/v1/categories", json={"name": "Spices"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_endpoint_list_categories(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user3")
    client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Dairy"},
    )
    response = client.get(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_endpoint_list_categories_search(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user4")
    client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Electronics"},
    )
    client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Clothing"},
    )
    response = client.get(
        "/api/v1/categories?search=Elect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Electronics"


def test_endpoint_get_category_by_id_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user5")
    cat = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Bakery"},
    ).json()
    response = client.get(
        f"/api/v1/categories/{cat['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Bakery"


def test_endpoint_get_category_by_id_not_found(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user6")
    response = client.get(
        "/api/v1/categories/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_endpoint_update_category_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user7")
    cat = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Old Cat"},
    ).json()
    response = client.put(
        f"/api/v1/categories/{cat['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Cat"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Cat"


def test_endpoint_update_category_duplicate_name(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user8")
    client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "First Cat"},
    )
    c2 = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Second Cat"},
    ).json()
    response = client.put(
        f"/api/v1/categories/{c2['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "First Cat"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CATEGORY_EXISTS"


def test_endpoint_delete_category_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user9")
    cat = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "To Del"},
    ).json()
    del_res = client.delete(
        f"/api/v1/categories/{cat['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200
    get_res = client.get(
        f"/api/v1/categories/{cat['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


def test_endpoint_delete_category_not_found(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "cat_user10")
    response = client.delete(
        "/api/v1/categories/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 4. Product CRUD & Permissions Tests
# ---------------------------------------------------------------------------


def test_endpoint_create_product_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "prod_creator", role_name="staff")
    cat = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Grains"},
    ).json()

    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category_id": cat["id"],
            "name": "মিনিকেট চাল",
            "unit": "kg",
            "purchase_price": "55.50",
            "sale_price": "65.00",
            "current_stock": "100.000",
            "low_stock_threshold": "10.000",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "মিনিকেট চাল"
    assert data["unit"] == "kg"
    assert data["category_id"] == cat["id"]
    # Verify Decimals are returned as strings
    assert data["purchase_price"] == "55.50"
    assert data["sale_price"] == "65.00"
    assert data["current_stock"] == "100.000"
    assert data["low_stock_threshold"] == "10.000"
    assert data["is_active"] is True


def test_endpoint_create_product_invalid_category(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "prod_user2", role_name="staff")
    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category_id": 9999,
            "name": "Test Product",
            "unit": "pcs",
            "sale_price": "20.00",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CATEGORY"


def test_endpoint_get_product_by_id_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "prod_user3", role_name="staff")
    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Mustard Oil", "unit": "liter", "sale_price": "220.00"},
    ).json()

    response = client.get(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Mustard Oil"
    assert response.json()["sale_price"] == "220.00"


def test_endpoint_get_product_by_id_not_found(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "prod_user4", role_name="staff")
    response = client.get(
        "/api/v1/products/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_endpoint_update_product_success(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "prod_user5", role_name="staff")
    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Sugar", "unit": "kg", "sale_price": "130.00"},
    ).json()

    response = client.put(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Brown Sugar", "sale_price": "145.50"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Brown Sugar"
    assert response.json()["sale_price"] == "145.50"


def test_endpoint_update_product_rejects_current_stock(
    client: TestClient, test_db_session: Session
):
    token = _create_user_with_role(client, test_db_session, "prod_user6", role_name="staff")
    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Salt", "unit": "kg", "sale_price": "40.00"},
    ).json()

    # ProductUpdate forbids current_stock -> returns 422
    response = client.patch(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_stock": "50.000"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. Role Permissions Tests (Owner vs Staff vs Others)
# ---------------------------------------------------------------------------


def test_endpoint_staff_can_create_and_edit_product(client: TestClient, test_db_session: Session):
    staff_token = _create_user_with_role(
        client, test_db_session, "staff_member", role_name="staff"
    )

    # Staff creates product
    create_res = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"name": "Flour", "unit": "kg", "sale_price": "50.00"},
    )
    assert create_res.status_code == 201
    prod_id = create_res.json()["id"]

    # Staff edits product
    edit_res = client.put(
        f"/api/v1/products/{prod_id}",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"sale_price": "55.00"},
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["sale_price"] == "55.00"


def test_endpoint_staff_cannot_delete_product(client: TestClient, test_db_session: Session):
    owner_token = _create_user_with_role(client, test_db_session, "the_owner", role_name="owner")
    staff_token = _create_user_with_role(client, test_db_session, "the_staff", role_name="staff")

    # Product created
    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Tea Leaves", "unit": "box", "sale_price": "180.00"},
    ).json()

    # Staff attempts to delete product -> 403 Forbidden
    del_res = client.delete(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert del_res.status_code == 403
    assert del_res.json() == {
        "error": {
            "code": "FORBIDDEN",
            "message": "Only an owner can delete products.",
        }
    }


def test_endpoint_viewer_cannot_create_or_edit_product(
    client: TestClient, test_db_session: Session
):
    owner_token = _create_user_with_role(
        client, test_db_session, "owner_for_viewer", role_name="owner"
    )
    viewer_token = _create_user_with_role(
        client, test_db_session, "the_viewer", role_name="viewer"
    )

    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Spices", "unit": "kg", "sale_price": "80.00"},
    ).json()

    # Viewer tries to create -> 403
    create_res = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"name": "Ginger", "unit": "kg", "sale_price": "90.00"},
    )
    assert create_res.status_code == 403
    assert create_res.json()["error"]["code"] == "FORBIDDEN"

    # Viewer tries to edit -> 403
    edit_res = client.put(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"sale_price": "85.00"},
    )
    assert edit_res.status_code == 403
    assert edit_res.json()["error"]["code"] == "FORBIDDEN"


def test_endpoint_owner_can_delete_product(client: TestClient, test_db_session: Session):
    owner_token = _create_user_with_role(client, test_db_session, "big_owner", role_name="owner")

    prod = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Lentils", "unit": "kg", "sale_price": "110.00"},
    ).json()

    # Owner deletes product -> 200 OK
    del_res = client.delete(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_res.status_code == 200
    assert del_res.json() == {"message": "Product deleted successfully."}

    # Soft delete: GET returns 404
    get_res = client.get(
        f"/api/v1/products/{prod['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert get_res.status_code == 404


# ---------------------------------------------------------------------------
# 6. Pagination, Search, and Category Filtering Tests
# ---------------------------------------------------------------------------


def test_endpoint_list_products_pagination(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "pagi_user", role_name="staff")

    for i in range(5):
        client.post(
            "/api/v1/products",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Item {i}", "unit": "pcs", "sale_price": f"{10 + i}.00"},
        )

    # Fetch page of size 2, skipping first 2
    response = client.get(
        "/api/v1/products?skip=2&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "Item 2"
    assert data["items"][1]["name"] == "Item 3"


def test_endpoint_list_products_search(client: TestClient, test_db_session: Session):
    token = _create_user_with_role(client, test_db_session, "search_user", role_name="staff")

    client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Miniket Rice", "unit": "kg", "sale_price": "65.00"},
    )
    client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Basmati Rice", "unit": "kg", "sale_price": "120.00"},
    )
    client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Soybean Oil", "unit": "liter", "sale_price": "190.00"},
    )

    response = client.get(
        "/api/v1/products?search=Rice",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    names = [p["name"] for p in data["items"]]
    assert "Miniket Rice" in names
    assert "Basmati Rice" in names
    assert "Soybean Oil" not in names


def test_endpoint_list_products_filter_by_category(
    client: TestClient, test_db_session: Session
):
    token = _create_user_with_role(client, test_db_session, "filter_user", role_name="staff")

    cat_drinks = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Drinks"},
    ).json()

    cat_snacks = client.post(
        "/api/v1/categories",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Snacks"},
    ).json()

    client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category_id": cat_drinks["id"],
            "name": "Orange Juice",
            "unit": "can",
            "sale_price": "50.00",
        },
    )
    client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category_id": cat_snacks["id"],
            "name": "Potato Chips",
            "unit": "pack",
            "sale_price": "25.00",
        },
    )

    # Filter by Drinks category
    response = client.get(
        f"/api/v1/products?category_id={cat_drinks['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Orange Juice"
    assert data["items"][0]["category_id"] == cat_drinks["id"]
