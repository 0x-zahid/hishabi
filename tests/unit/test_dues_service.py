"""Unit tests for the shared dues service.

Owner: Zahid. Module 2 (sales and customer dues).
Complies with PROJECT_RULES.md and docs/schema.md.

This service is the **shared contract**: it is the single source of truth for
a customer's outstanding due, and Azaz (237) is expected to call it from
``app/services/report_service.py``.

Tests cover:
- ``get_customer_due`` implements R16 exactly.
- ``get_customer_due_breakdown`` returns the component figures.
- The breakdown and ``get_customer_due`` never disagree.
- ``get_all_customer_dues`` omits customers with no ledger and sorts by due.
- ``get_customer_payment_history`` returns the payments newest first.
- ``get_customer_sales`` and ``get_customer_summary`` feed Azaz's customer
  history endpoint.
- Every amount is a ``Decimal``, never a ``float``.
- The service never writes and never raises an ``HTTPException``.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.payment import Payment
from app.models.product import Product
from app.services import dues_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_customer(db: Session, name: str) -> Customer:
    """Create a customer."""
    customer = Customer(name=name, phone=None, is_active=True)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _make_product(db: Session, name: str) -> Product:
    """Create a product with stock."""
    product = Product(
        category_id=None,
        name=name,
        unit="kg",
        purchase_price=Decimal("50.00"),
        sale_price=Decimal("60.00"),
        current_stock=Decimal("100.000"),
        low_stock_threshold=Decimal("5.000"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _add_payment(db: Session, customer: Customer, amount: str, sale_id: int | None = None):
    """Insert a payment row directly."""
    payment = Payment(
        customer_id=customer.id,
        user_id=None,
        sale_id=sale_id,
        amount=Decimal(amount),
        payment_method="cash",
        note=None,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


# ---------------------------------------------------------------------------
# get_customer_due
# ---------------------------------------------------------------------------


def test_get_customer_due_is_zero_without_any_ledger(test_db_session: Session):
    """A customer with no sales and no payments owes nothing."""
    customer = _make_customer(test_db_session, "No Ledger Customer")

    due = dues_service.get_customer_due(test_db_session, customer.id)

    assert due == Decimal("0.00")
    assert isinstance(due, Decimal)


def test_get_customer_due_follows_r16(test_db_session: Session):
    """R16: credit-sale dues minus payments."""
    customer = _make_customer(test_db_session, "R16 Customer")
    product = _make_product(test_db_session, "Rice")

    # A credit sale of 5 x 60.00 = 300.00, all on account.
    from app.models.sale import Sale
    from app.models.sale_item import SaleItem

    sale = Sale(
        customer_id=customer.id,
        user_id=None,
        payment_type="credit",
        total_amount=Decimal("300.00"),
        paid_amount=Decimal("0.00"),
        due_amount=Decimal("300.00"),
    )
    test_db_session.add(sale)
    test_db_session.flush()
    sale.items.append(
        SaleItem(
            product_id=product.id,
            quantity=Decimal("5.000"),
            unit_price=Decimal("60.00"),
            line_total=Decimal("300.00"),
        )
    )
    test_db_session.commit()

    assert dues_service.get_customer_due(test_db_session, customer.id) == Decimal("300.00")

    _add_payment(test_db_session, customer, "120.00")

    assert dues_service.get_customer_due(test_db_session, customer.id) == Decimal("180.00")


def test_cash_sales_do_not_create_a_due(test_db_session: Session):
    """A cash sale is never on account, so it adds no due."""
    customer = _make_customer(test_db_session, "Cash Buyer")
    product = _make_product(test_db_session, "Rice")

    from app.models.sale import Sale
    from app.models.sale_item import SaleItem

    sale = Sale(
        customer_id=customer.id,
        user_id=None,
        payment_type="cash",
        total_amount=Decimal("300.00"),
        paid_amount=Decimal("300.00"),
        due_amount=Decimal("0.00"),
    )
    test_db_session.add(sale)
    test_db_session.flush()
    sale.items.append(
        SaleItem(
            product_id=product.id,
            quantity=Decimal("5.000"),
            unit_price=Decimal("60.00"),
            line_total=Decimal("300.00"),
        )
    )
    test_db_session.commit()

    assert dues_service.get_customer_due(test_db_session, customer.id) == Decimal("0.00")


# ---------------------------------------------------------------------------
# get_customer_due_breakdown
# ---------------------------------------------------------------------------


def test_due_breakdown_reports_the_components(test_db_session: Session):
    """The breakdown shows how the due was reached."""
    customer = _make_customer(test_db_session, "Breakdown Customer")

    from app.models.sale import Sale

    sale = Sale(
        customer_id=customer.id,
        user_id=None,
        payment_type="credit",
        total_amount=Decimal("300.00"),
        paid_amount=Decimal("50.00"),
        due_amount=Decimal("250.00"),
    )
    test_db_session.add(sale)
    test_db_session.commit()
    _add_payment(test_db_session, customer, "100.00", sale_id=sale.id)

    breakdown = dues_service.get_customer_due_breakdown(test_db_session, customer.id)

    assert breakdown["customer_id"] == customer.id
    assert breakdown["total_credit_sales"] == Decimal("300.00")
    assert breakdown["total_paid"] == Decimal("150.00")  # 50.00 at the counter + 100.00 paid
    assert breakdown["current_due"] == Decimal("150.00")
    assert breakdown["sale_count"] == 1
    assert breakdown["payment_count"] == 1


def test_breakdown_and_due_never_disagree(test_db_session: Session):
    """``current_due`` in the breakdown equals ``get_customer_due()``."""
    customer = _make_customer(test_db_session, "Agreement Customer")

    from app.models.sale import Sale

    sale = Sale(
        customer_id=customer.id,
        user_id=None,
        payment_type="credit",
        total_amount=Decimal("500.00"),
        paid_amount=Decimal("100.00"),
        due_amount=Decimal("400.00"),
    )
    test_db_session.add(sale)
    test_db_session.commit()
    _add_payment(test_db_session, customer, "250.00")

    breakdown = dues_service.get_customer_due_breakdown(test_db_session, customer.id)
    direct = dues_service.get_customer_due(test_db_session, customer.id)

    assert breakdown["current_due"] == direct


# ---------------------------------------------------------------------------
# get_all_customer_dues
# ---------------------------------------------------------------------------


def test_get_all_customer_dues_omits_customers_without_a_ledger(test_db_session: Session):
    """A customer with no credit sales and no payments is omitted."""
    clean = _make_customer(test_db_session, "Clean Customer")
    owing = _make_customer(test_db_session, "Owing Customer")

    from app.models.sale import Sale

    sale = Sale(
        customer_id=owing.id,
        user_id=None,
        payment_type="credit",
        total_amount=Decimal("300.00"),
        paid_amount=Decimal("0.00"),
        due_amount=Decimal("300.00"),
    )
    test_db_session.add(sale)
    test_db_session.commit()

    rows = dues_service.get_all_customer_dues(test_db_session)

    assert [row["customer_id"] for row in rows] == [owing.id]
    assert clean.id not in [row["customer_id"] for row in rows]
    assert rows[0]["customer_name"] == "Owing Customer"
    assert rows[0]["phone"] is None
    assert rows[0]["current_due"] == Decimal("300.00")


def test_get_all_customer_dues_is_sorted_by_due_descending(test_db_session: Session):
    """The biggest due comes first."""
    small = _make_customer(test_db_session, "Small Due")
    big = _make_customer(test_db_session, "Big Due")
    middle = _make_customer(test_db_session, "Middle Due")

    from app.models.sale import Sale

    for customer, amount in ((small, "100.00"), (big, "900.00"), (middle, "400.00")):
        test_db_session.add(
            Sale(
                customer_id=customer.id,
                user_id=None,
                payment_type="credit",
                total_amount=Decimal(amount),
                paid_amount=Decimal("0.00"),
                due_amount=Decimal(amount),
            )
        )
    test_db_session.commit()

    rows = dues_service.get_all_customer_dues(test_db_session)

    assert [row["customer_name"] for row in rows] == ["Big Due", "Middle Due", "Small Due"]
    assert [row["current_due"] for row in rows] == [
        Decimal("900.00"),
        Decimal("400.00"),
        Decimal("100.00"),
    ]


def test_get_all_customer_dues_includes_a_customer_with_only_payments(
    test_db_session: Session,
):
    """A customer with a payment history is included even with no credit sale.

    This state cannot be reached through the API (R17 refuses a payment larger
    than the due, and R19 never deletes a sale), so it only exists when rows
    are written directly. The row must still be reported, and the due follows
    R16's formula literally: credit-sale dues minus payments.
    """
    customer = _make_customer(test_db_session, "Payment Only Customer")
    _add_payment(test_db_session, customer, "50.00")

    rows = dues_service.get_all_customer_dues(test_db_session)

    assert len(rows) == 1
    assert rows[0]["customer_id"] == customer.id
    assert rows[0]["sale_count"] == 0
    assert rows[0]["payment_count"] == 1
    assert rows[0]["total_paid"] == Decimal("50.00")
    assert rows[0]["current_due"] == Decimal("-50.00")


# ---------------------------------------------------------------------------
# get_customer_payment_history
# ---------------------------------------------------------------------------


def test_payment_history_is_newest_first(test_db_session: Session):
    """The history lists the payments newest first."""
    customer = _make_customer(test_db_session, "History Customer")
    _add_payment(test_db_session, customer, "10.00")
    _add_payment(test_db_session, customer, "20.00")
    _add_payment(test_db_session, customer, "30.00")

    history = dues_service.get_customer_payment_history(test_db_session, customer.id)

    assert [entry["amount"] for entry in history] == [
        Decimal("30.00"),
        Decimal("20.00"),
        Decimal("10.00"),
    ]


def test_payment_history_entries_have_the_contract_shape(test_db_session: Session):
    """Every entry carries the documented keys."""
    customer = _make_customer(test_db_session, "Shape Customer")
    payment = _add_payment(test_db_session, customer, "42.50")

    history = dues_service.get_customer_payment_history(test_db_session, customer.id)

    assert len(history) == 1
    entry = history[0]
    assert set(entry) == {
        "id",
        "customer_id",
        "amount",
        "payment_method",
        "note",
        "sale_id",
        "created_at",
    }
    assert entry["id"] == payment.id
    assert entry["customer_id"] == customer.id
    assert entry["amount"] == Decimal("42.50")
    assert entry["payment_method"] == "cash"
    assert entry["sale_id"] is None
    assert entry["created_at"] is not None


def test_payment_history_of_a_customer_without_payments_is_empty(test_db_session: Session):
    """A customer with no payments has an empty history."""
    customer = _make_customer(test_db_session, "No Payments Customer")

    history = dues_service.get_customer_payment_history(test_db_session, customer.id)

    assert history == []


# ---------------------------------------------------------------------------
# get_customer_sales and get_customer_summary
# ---------------------------------------------------------------------------


def _add_credit_sale(db: Session, customer: Customer, product: Product, total: str, paid: str):
    """Insert a credit sale with one line directly."""
    from app.models.sale import Sale
    from app.models.sale_item import SaleItem

    sale = Sale(
        customer_id=customer.id,
        user_id=None,
        payment_type="credit",
        total_amount=Decimal(total),
        paid_amount=Decimal(paid),
        due_amount=Decimal(total) - Decimal(paid),
    )
    db.add(sale)
    db.flush()
    sale.items.append(
        SaleItem(
            product_id=product.id,
            quantity=Decimal("1.000"),
            unit_price=Decimal(total),
            line_total=Decimal(total),
        )
    )
    db.commit()
    return sale


def test_get_customer_sales_returns_the_sales_newest_first(test_db_session: Session):
    """The customer sale list carries the header and the lines."""
    customer = _make_customer(test_db_session, "Sale History Customer")
    product = _make_product(test_db_session, "Rice")

    _add_credit_sale(test_db_session, customer, product, "100.00", "0.00")
    _add_credit_sale(test_db_session, customer, product, "250.00", "50.00")

    sales = dues_service.get_customer_sales(test_db_session, customer.id)

    assert len(sales) == 2
    assert sales[0]["total_amount"] == Decimal("250.00")
    assert sales[0]["due_amount"] == Decimal("200.00")
    assert sales[0]["payment_type"] == "credit"
    assert sales[1]["total_amount"] == Decimal("100.00")
    assert len(sales[0]["items"]) == 1
    assert sales[0]["items"][0]["product_id"] == product.id
    assert sales[0]["items"][0]["line_total"] == Decimal("250.00")
    assert sales[0]["items"][0]["product_name"] == "Rice"


def test_get_customer_sales_of_a_customer_without_sales_is_empty(test_db_session: Session):
    """A customer with no sales has an empty sale list."""
    customer = _make_customer(test_db_session, "No Sale Customer")

    assert dues_service.get_customer_sales(test_db_session, customer.id) == []


def test_get_customer_summary_reports_the_money(test_db_session: Session):
    """The summary feeds Azaz's ``CustomerSummaryOut``."""
    customer = _make_customer(test_db_session, "Summary Customer")
    product = _make_product(test_db_session, "Rice")

    _add_credit_sale(test_db_session, customer, product, "300.00", "100.00")
    _add_payment(test_db_session, customer, "50.00")

    summary = dues_service.get_customer_summary(test_db_session, customer.id)

    assert summary["total_sales"] == Decimal("300.00")
    assert summary["total_paid"] == Decimal("150.00")  # 100.00 at the counter + 50.00 paid
    assert summary["current_due"] == Decimal("150.00")


# ---------------------------------------------------------------------------
# Contract guarantees
# ---------------------------------------------------------------------------


def test_the_service_returns_decimals_and_never_floats(test_db_session: Session):
    """Money is ``Decimal`` throughout, never ``float``."""
    customer = _make_customer(test_db_session, "Decimal Customer")
    _add_payment(test_db_session, customer, "10.00")

    due = dues_service.get_customer_due(test_db_session, customer.id)
    breakdown = dues_service.get_customer_due_breakdown(test_db_session, customer.id)
    rows = dues_service.get_all_customer_dues(test_db_session)
    history = dues_service.get_customer_payment_history(test_db_session, customer.id)

    amounts = [
        due,
        breakdown["total_credit_sales"],
        breakdown["total_paid"],
        breakdown["current_due"],
        rows[0]["current_due"],
        history[0]["amount"],
    ]
    for amount in amounts:
        assert isinstance(amount, Decimal)
        assert not isinstance(amount, float)


def test_the_service_never_raises_an_http_exception(test_db_session: Session):
    """The service is a pure query: the router raises the HTTP errors.

    Asking for a customer that does not exist returns zeros instead of
    raising, so a caller cannot accidentally turn a missing row into a 500.
    """
    due = dues_service.get_customer_due(test_db_session, 999999)
    breakdown = dues_service.get_customer_due_breakdown(test_db_session, 999999)
    rows = dues_service.get_all_customer_dues(test_db_session)
    history = dues_service.get_customer_payment_history(test_db_session, 999999)

    assert due == Decimal("0.00")
    assert breakdown["current_due"] == Decimal("0.00")
    assert breakdown["sale_count"] == 0
    assert rows == []
    assert history == []


# ---------------------------------------------------------------------------
# The contract with Azaz's report schema
# ---------------------------------------------------------------------------


def test_the_rows_map_onto_azazs_due_report_schema(test_db_session: Session):
    """Each row must fill Azaz's ``CustomerDueItem`` without translation.

    ``app/services/report_service.py`` builds its due report out of
    ``CustomerDueItem`` (Azaz's schema in ``app/schemas/report.py``). This test
    proves the shared contract fits that schema exactly: every field the
    report needs is present, with the right type, and no money is lost on the
    way in.
    """
    from app.schemas.report import CustomerDueItem

    customer = _make_customer(test_db_session, "Report Customer")
    product = _make_product(test_db_session, "Rice")

    # A credit sale of 200.00 with 50.00 paid at the counter, then a later
    # payment of 30.00: the customer still owes 120.00.
    _add_credit_sale(test_db_session, customer, product, "200.00", "50.00")
    _add_payment(test_db_session, customer, "30.00")

    rows = dues_service.get_all_customer_dues(test_db_session)
    assert len(rows) == 1
    row = rows[0]

    # The exact construction Azaz's get_due_report() performs.
    item = CustomerDueItem(
        customer_id=row["customer_id"],
        customer_name=row["customer_name"],
        phone=row["phone"],
        total_sales=row["total_credit_sales"],
        total_paid=row["total_paid"],
        current_due=row["current_due"],
    )

    assert item.customer_id == customer.id
    assert item.customer_name == "Report Customer"
    assert item.total_sales == Decimal("200.00")
    # 50.00 paid at the counter plus the 30.00 payment.
    assert item.total_paid == Decimal("80.00")
    assert item.current_due == Decimal("120.00")

    # The schema serialises every amount as a two-decimal string, so the
    # report shows a money value and never a float.
    assert item.model_dump()["current_due"] == "120.00"
