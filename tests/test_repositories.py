from pathlib import Path

from src.data.db import ingest_csvs
from src.data.repositories import DemoIdentity, get_owned_order, search_products


def test_product_availability_filters_and_promotion_math(dataset_dir: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "folder?hash#marker" / "app.db"
    ingest_csvs(dataset_dir, db_path)

    available = search_products(db_path, available_only=True)
    assert {product.product_id for product in available} == {"p1", "p5"}
    first = next(product for product in available if product.product_id == "p1")
    assert first.description == "Modelo de entrada"
    assert first.specs == {"strings": 6}
    promo = search_products(db_path, active_promotion=True)
    assert len(promo) == 1
    assert promo[0].product_id == "p5"
    assert promo[0].price_cents == 19999
    assert promo[0].promotional_price_cents == 16999
    filtered = search_products(
        db_path,
        category="Violões",
        min_price_cents=16000,
        max_price_cents=18000,
        available_only=True,
    )
    assert {product.product_id for product in filtered} == {"p5"}


def test_product_search_uses_parameters_and_limit(dataset_dir: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    ingest_csvs(dataset_dir, db_path)

    malicious_query = "' OR 1=1 --"
    assert search_products(db_path, query=malicious_query, available_only=False) == []
    assert len(search_products(db_path, available_only=False, limit=1)) == 1


def test_order_lookup_checks_backend_identity_and_minimizes_fields(
    dataset_dir: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "app.db"
    ingest_csvs(dataset_dir, db_path)

    owner = DemoIdentity(customer_id="cust1")
    other = DemoIdentity(customer_id="cust2")
    assert get_owned_order(db_path, "ord1", owner).order_id == "ord1"
    assert get_owned_order(db_path, "ord2", owner).order_id == "ord2"
    assert get_owned_order(db_path, "ord1", other) is None
    assert get_owned_order(db_path, "missing", owner) is None
    order = get_owned_order(db_path, "ord1", owner)
    assert set(order.to_dict()) == {
        "order_id", "order_date", "status", "total_cents", "payment_method",
        "tracking_code", "estimated_delivery", "items",
    }
    assert [(item.product_name, item.quantity) for item in order.items] == [("Violão Inicial", 1)]
