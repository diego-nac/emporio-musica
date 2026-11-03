import csv
from pathlib import Path

import pytest


HEADERS = {
    "categories": ["category_id", "name", "description"],
    "customers": ["customer_id", "name", "phone", "email", "city"],
    "order_items": ["order_id", "quantity", "product_id"],
    "orders": [
        "order_id",
        "customer_id",
        "order_date",
        "status",
        "total_brl",
        "payment_method",
        "tracking_code",
        "estimated_delivery",
        "notes",
    ],
    "products": [
        "product_id",
        "price_brl",
        "name",
        "category_id",
        "description",
        "stock_quantity",
        "status",
        "specs",
        "created_at",
    ],
    "promotions": [
        "promotion_id",
        "product_id",
        "discount_percent",
        "description",
        "is_active",
    ],
}


ROWS = {
    "categories": [
        {"category_id": "cat1", "name": "Violões", "description": "Cordas"},
        {"category_id": "cat2", "name": "Teclas", "description": "Teclas"},
    ],
    "customers": [
        {"customer_id": "cust1", "name": "Fixture Um", "phone": "", "email": "", "city": ""},
        {"customer_id": "cust2", "name": "Fixture Dois", "phone": "", "email": "", "city": ""},
    ],
    "order_items": [
        {"order_id": "ord1", "quantity": "1", "product_id": "p1"},
        {"order_id": "ord2", "quantity": "1", "product_id": "p2"},
        {"order_id": "ord3", "quantity": "1", "product_id": "p3"},
    ],
    "orders": [
        {"order_id": "ord1", "customer_id": "cust1", "order_date": "2026-01-01", "status": "shipped", "total_brl": "100.00", "payment_method": "PIX", "tracking_code": "", "estimated_delivery": "", "notes": "do not expose"},
        {"order_id": "ord2", "customer_id": "cust1", "order_date": "2026-01-02", "status": "pending", "total_brl": "200.50", "payment_method": "card", "tracking_code": "BR123", "estimated_delivery": "2026-01-10", "notes": "private"},
        {"order_id": "ord3", "customer_id": "cust2", "order_date": "2026-01-03", "status": "delivered", "total_brl": "300.00", "payment_method": "card", "tracking_code": "", "estimated_delivery": "", "notes": "private"},
    ],
    "products": [
        {"product_id": "p1", "price_brl": "100.00", "name": "Violão Inicial", "category_id": "cat1", "description": "Modelo de entrada", "stock_quantity": "3", "status": "active", "specs": '{"strings": 6}', "created_at": "2025-01-01"},
        {"product_id": "p2", "price_brl": "0.10", "name": "Violão Sem Estoque", "category_id": "cat1", "description": "Esgotado", "stock_quantity": "0", "status": "active", "specs": "{}", "created_at": "2025-01-01"},
        {"product_id": "p3", "price_brl": "150.00", "name": "Teclado Futuro", "category_id": "cat2", "description": "Lançamento", "stock_quantity": "10", "status": "coming_soon", "specs": "{}", "created_at": "2025-01-01"},
        {"product_id": "p4", "price_brl": "175.00", "name": "Teclado Antigo", "category_id": "cat2", "description": "Descontinuado", "stock_quantity": "2", "status": "discontinued", "specs": "{}", "created_at": "2025-01-01"},
        {"product_id": "p5", "price_brl": "199.99", "name": "Violão Promocional", "category_id": "cat1", "description": "Oferta", "stock_quantity": "2", "status": "active", "specs": "{}", "created_at": "2025-01-01"},
    ],
    "promotions": [
        {"promotion_id": "promo1", "product_id": "p5", "discount_percent": "15", "description": "Oferta ativa", "is_active": "true"},
        {"promotion_id": "promo2", "product_id": "p1", "discount_percent": "20", "description": "Oferta inativa", "is_active": "false"},
    ],
}


def write_dataset(directory: Path, rows: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    selected_rows = rows or ROWS
    for table, headers in HEADERS.items():
        with (directory / f"desafio_tecnico_ai_eng - {table}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as output:
            writer = csv.DictWriter(output, fieldnames=headers)
            writer.writeheader()
            writer.writerows(selected_rows[table])
    return directory


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    return write_dataset(tmp_path / "source")
