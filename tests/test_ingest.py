import sqlite3
from pathlib import Path

import pytest

from src.data.db import IngestError, ingest_csvs
from tests.conftest import ROWS, write_dataset


def test_ingestion_is_repeatable_and_stores_brl_as_cents(dataset_dir: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"

    first = ingest_csvs(dataset_dir, db_path)
    second = ingest_csvs(dataset_dir, db_path)

    assert first.rows_by_table == second.rows_by_table
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 5
        assert connection.execute(
            "SELECT price_cents FROM products WHERE product_id = ?", ("p5",)
        ).fetchone()[0] == 19999
        assert connection.execute(
            "SELECT total_cents FROM orders WHERE order_id = ?", ("ord2",)
        ).fetchone()[0] == 20050
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("invalid_field", ["specs", "category_id", "order_date"])
def test_failed_reimport_preserves_previous_database(
    dataset_dir: Path, tmp_path: Path, invalid_field: str
) -> None:
    db_path = tmp_path / "app.db"
    ingest_csvs(dataset_dir, db_path)
    previous_bytes = db_path.read_bytes()

    changed = {table: [dict(row) for row in table_rows] for table, table_rows in ROWS.items()}
    if invalid_field == "specs":
        changed["products"][0]["specs"] = "not-json"
    elif invalid_field == "category_id":
        changed["products"][0]["category_id"] = "missing-category"
    else:
        changed["orders"][0]["order_date"] = "not-a-date"
    write_dataset(dataset_dir, changed)

    with pytest.raises(IngestError):
        ingest_csvs(dataset_dir, db_path)

    assert db_path.read_bytes() == previous_bytes


def test_multiple_active_promotions_for_one_product_preserve_previous_database(
    dataset_dir: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "app.db"
    ingest_csvs(dataset_dir, db_path)
    previous_bytes = db_path.read_bytes()
    changed = {table: [dict(row) for row in table_rows] for table, table_rows in ROWS.items()}
    changed["promotions"].append(
        {"promotion_id": "promo3", "product_id": "p5", "discount_percent": "10",
         "description": "Second active offer", "is_active": "true"}
    )
    write_dataset(dataset_dir, changed)

    with pytest.raises(IngestError, match="multiple active promotions"):
        ingest_csvs(dataset_dir, db_path)

    assert db_path.read_bytes() == previous_bytes
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 5


def test_missing_csv_header_fails_before_touching_existing_database(
    dataset_dir: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "app.db"
    ingest_csvs(dataset_dir, db_path)
    previous_bytes = db_path.read_bytes()
    (dataset_dir / "desafio_tecnico_ai_eng - products.csv").write_text(
        "wrong,header\n1,2\n", encoding="utf-8"
    )

    with pytest.raises(IngestError, match="products"):
        ingest_csvs(dataset_dir, db_path)

    assert db_path.read_bytes() == previous_bytes
