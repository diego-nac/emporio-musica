import csv
import json
import os
import sqlite3
import tempfile
from datetime import date, datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IngestReport:
    rows_by_table: dict[str, int]
    database_path: str


TABLES = {
    "categories": ("category_id", "name", "description"),
    "customers": ("customer_id", "name", "phone", "email", "city"),
    "order_items": ("order_id", "quantity", "product_id"),
    "orders": (
        "order_id",
        "customer_id",
        "order_date",
        "status",
        "total_brl",
        "payment_method",
        "tracking_code",
        "estimated_delivery",
        "notes",
    ),
    "products": (
        "product_id",
        "price_brl",
        "name",
        "category_id",
        "description",
        "stock_quantity",
        "status",
        "specs",
        "created_at",
    ),
    "promotions": ("promotion_id", "product_id", "discount_percent", "description", "is_active"),
}


class IngestError(ValueError):
    """Raised when a source CSV does not match the expected schema or values."""


def _source_files(source_dir: Path) -> dict[str, Path]:
    if not source_dir.is_dir():
        raise IngestError(f"Source directory not found: {source_dir}")
    files = {table: [] for table in TABLES}
    for path in source_dir.glob("*.csv"):
        lower_name = path.name.lower()
        for table in TABLES:
            if lower_name.endswith(f"{table}.csv"):
                files[table].append(path)
    missing = [table for table, paths in files.items() if not paths]
    ambiguous = [table for table, paths in files.items() if len(paths) > 1]
    if missing or ambiguous:
        details = []
        if missing:
            details.append(f"missing tables: {', '.join(missing)}")
        if ambiguous:
            details.append(f"multiple files for tables: {', '.join(ambiguous)}")
        raise IngestError("Invalid CSV set: " + "; ".join(details))
    return {table: paths[0] for table, paths in files.items()}


def _money_to_cents(raw: str, location: str) -> int:
    value = raw.strip().replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        value = value.replace(",", ".")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise IngestError(f"{location}: invalid monetary amount") from error
    if not amount.is_finite() or amount < 0:
        raise IngestError(f"{location}: monetary amount must be finite and non-negative")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise IngestError(f"{location}: monetary amount has more than two decimal places")
    return int(cents)


def _percent_to_basis_points(raw: str, location: str) -> int:
    try:
        value = Decimal(raw.strip().replace(",", "."))
    except InvalidOperation as error:
        raise IngestError(f"{location}: invalid discount percentage") from error
    if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
        raise IngestError(f"{location}: discount percentage must be between 0 and 100")
    basis_points = value * 100
    if basis_points != basis_points.to_integral_value():
        raise IngestError(f"{location}: discount percentage has more than two decimal places")
    return int(basis_points)


def _integer(raw: str, location: str, minimum: int = 0) -> int:
    try:
        value = int(raw.strip())
    except (TypeError, ValueError) as error:
        raise IngestError(f"{location}: invalid integer") from error
    if value < minimum:
        raise IngestError(f"{location}: integer must be at least {minimum}")
    return value


def _boolean(raw: str, location: str) -> int:
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes", "sim"}:
        return 1
    if normalized in {"false", "0", "no", "não", "nao"}:
        return 0
    raise IngestError(f"{location}: invalid boolean")


def _iso_date(raw: str, location: str, allow_empty: bool = False) -> str | None:
    value = raw.strip()
    if value == "" and allow_empty:
        return None
    if value == "":
        raise IngestError(f"{location}: date is empty")
    try:
        date.fromisoformat(value)
        return value
    except ValueError:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError as error:
            raise IngestError(f"{location}: expected an ISO date or datetime") from error


def _required(row: dict[str, str], column: str, location: str) -> str:
    value = row.get(column)
    if value is None or value.strip() == "":
        raise IngestError(f"{location}: required value is empty")
    return value.strip()


def _read_table(table: str, path: Path) -> list[dict[str, Any]]:
    expected = TABLES[table]
    parsed: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise IngestError(f"Cannot read CSV for {table}") from error
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise IngestError(f"{path.name}: invalid or duplicate header")
        if set(reader.fieldnames) != set(expected):
            missing = sorted(set(expected) - set(reader.fieldnames))
            extra = sorted(set(reader.fieldnames) - set(expected))
            raise IngestError(
                f"{path.name}: invalid header (missing: {missing}; extra: {extra})"
            )
        for line_number, raw_row in enumerate(reader, start=2):
            location = f"{path.name}:{line_number}"
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise IngestError(f"{location}: row has a different number of columns")
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            row = {key: value.strip() for key, value in raw_row.items()}
            try:
                if table == "categories":
                    parsed.append({
                        "category_id": _required(row, "category_id", location),
                        "name": _required(row, "name", location),
                        "description": row["description"],
                    })
                elif table == "customers":
                    parsed.append({
                        "customer_id": _required(row, "customer_id", location),
                        "name": _required(row, "name", location),
                        "phone": row["phone"],
                        "email": row["email"],
                        "city": row["city"],
                    })
                elif table == "order_items":
                    parsed.append({
                        "order_id": _required(row, "order_id", location),
                        "quantity": _integer(row["quantity"], f"{location} quantity", 1),
                        "product_id": _required(row, "product_id", location),
                    })
                elif table == "orders":
                    parsed.append({
                        "order_id": _required(row, "order_id", location),
                        "customer_id": _required(row, "customer_id", location),
                        "order_date": _iso_date(row["order_date"], f"{location} order_date"),
                        "status": _required(row, "status", location),
                        "total_cents": _money_to_cents(row["total_brl"], f"{location} total_brl"),
                        "payment_method": _required(row, "payment_method", location),
                        "tracking_code": row["tracking_code"] or None,
                        "estimated_delivery": _iso_date(
                            row["estimated_delivery"], f"{location} estimated_delivery", allow_empty=True
                        ),
                        "notes": row["notes"],
                    })
                elif table == "products":
                    try:
                        specs = json.loads(_required(row, "specs", location))
                    except json.JSONDecodeError as error:
                        raise IngestError(f"{location} specs: invalid JSON") from error
                    if not isinstance(specs, dict):
                        raise IngestError(f"{location} specs: expected a JSON object")
                    parsed.append({
                        "product_id": _required(row, "product_id", location),
                        "price_cents": _money_to_cents(row["price_brl"], f"{location} price_brl"),
                        "name": _required(row, "name", location),
                        "category_id": _required(row, "category_id", location),
                        "description": row["description"],
                        "stock_quantity": _integer(row["stock_quantity"], f"{location} stock_quantity"),
                        "status": _required(row, "status", location),
                        "specs": json.dumps(specs, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        "created_at": _iso_date(row["created_at"], f"{location} created_at"),
                    })
                elif table == "promotions":
                    parsed.append({
                        "promotion_id": _required(row, "promotion_id", location),
                        "product_id": _required(row, "product_id", location),
                        "discount_basis_points": _percent_to_basis_points(
                            row["discount_percent"], f"{location} discount_percent"
                        ),
                        "description": row["description"],
                        "is_active": _boolean(row["is_active"], f"{location} is_active"),
                    })
            except IngestError:
                raise
            except (KeyError, TypeError, ValueError) as error:
                raise IngestError(f"{location}: invalid value for table {table}") from error
    return parsed


SCHEMA = """
CREATE TABLE categories (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    name TEXT NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    description TEXT NOT NULL,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status TEXT NOT NULL,
    specs TEXT NOT NULL CHECK (json_valid(specs)),
    created_at TEXT NOT NULL
);
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    payment_method TEXT NOT NULL,
    tracking_code TEXT,
    estimated_delivery TEXT,
    notes TEXT NOT NULL
);
CREATE TABLE order_items (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    PRIMARY KEY (order_id, product_id)
);
CREATE TABLE promotions (
    promotion_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    discount_basis_points INTEGER NOT NULL CHECK (discount_basis_points BETWEEN 0 AND 10000),
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
);
CREATE INDEX idx_products_category_status_stock ON products(category_id, status, stock_quantity);
CREATE INDEX idx_promotions_product_active ON promotions(product_id, is_active);
CREATE INDEX idx_orders_customer ON orders(customer_id);
"""


INSERTS = {
    "categories": "INSERT INTO categories VALUES (:category_id, :name, :description)",
    "customers": "INSERT INTO customers VALUES (:customer_id, :name, :phone, :email, :city)",
    "order_items": "INSERT INTO order_items VALUES (:order_id, :quantity, :product_id)",
    "orders": "INSERT INTO orders VALUES (:order_id, :customer_id, :order_date, :status, :total_cents, :payment_method, :tracking_code, :estimated_delivery, :notes)",
    "products": "INSERT INTO products VALUES (:product_id, :price_cents, :name, :category_id, :description, :stock_quantity, :status, :specs, :created_at)",
    "promotions": "INSERT INTO promotions VALUES (:promotion_id, :product_id, :discount_basis_points, :description, :is_active)",
}

INSERT_ORDER = ("categories", "customers", "products", "orders", "order_items", "promotions")


def ingest_csvs(source_dir: Path, db_path: Path) -> IngestReport:
    """Validate all source tables, build a temporary database, then atomically replace the target."""
    source_dir = Path(source_dir)
    db_path = Path(db_path)
    source_files = _source_files(source_dir)
    tables = {name: _read_table(name, source_files[name]) for name in TABLES}
    active_promotions_by_product: set[str] = set()
    for promotion in tables["promotions"]:
        if promotion["is_active"]:
            product_id = promotion["product_id"]
            if product_id in active_promotions_by_product:
                raise IngestError("Invalid promotion data: multiple active promotions for one product")
            active_promotions_by_product.add(product_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{db_path.name}.", suffix=".tmp", dir=db_path.parent, delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
        connection = sqlite3.connect(temp_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(SCHEMA)
            with connection:
                for table in INSERT_ORDER:
                    connection.executemany(INSERTS[table], tables[table])
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise IngestError("Imported data contains invalid foreign-key references")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise IngestError("Temporary database failed integrity check")
        except sqlite3.Error as error:
            raise IngestError("SQLite rejected the imported data") from error
        finally:
            connection.close()
        with temp_path.open("rb") as database_file:
            os.fsync(database_file.fileno())
        os.replace(temp_path, db_path)
        temp_path = None
    except OSError as error:
        raise IngestError("Could not atomically write the target database") from error
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return IngestReport(
        rows_by_table={table: len(rows) for table, rows in tables.items()},
        database_path=str(db_path),
    )
