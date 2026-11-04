import json
import sqlite3
from contextvars import ContextVar
from contextlib import closing
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sql_trace: ContextVar[list[dict] | None] = ContextVar("sql_trace", default=None)


def _record_sql(sql: str, parameters: list | tuple, *, private: bool = False) -> None:
    trace = sql_trace.get()
    if trace is not None:
        trace.append({"type": "sql", "sql": sql.strip(), "parameters": ["[protegido]"] * len(parameters) if private else list(parameters)})


@dataclass(frozen=True)
class DemoIdentity:
    customer_id: str


@dataclass(frozen=True)
class ProductSummary:
    product_id: str
    name: str
    category: str
    price_cents: int
    stock_quantity: int
    status: str
    description: str
    specs: dict
    promotion_discount_percent: Decimal | None
    promotional_price_cents: int | None


@dataclass(frozen=True)
class OrderItemSummary:
    product_name: str
    quantity: int


@dataclass(frozen=True)
class OrderSummary:
    order_id: str
    order_date: str
    status: str
    total_cents: int
    payment_method: str
    tracking_code: str | None
    estimated_delivery: str | None
    items: tuple[OrderItemSummary, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    database_uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def search_products(
    db_path: Path,
    query: str | None = None,
    category: str | None = None,
    min_price_cents: int | None = None,
    max_price_cents: int | None = None,
    active_promotion: bool | None = None,
    available_only: bool = True,
    limit: int = 5,
) -> list[ProductSummary]:
    """Search the local catalog with bound parameters and return minimal product details."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if min_price_cents is not None and min_price_cents < 0:
        raise ValueError("min_price_cents must be non-negative")
    if max_price_cents is not None and max_price_cents < 0:
        raise ValueError("max_price_cents must be non-negative")
    if min_price_cents is not None and max_price_cents is not None and min_price_cents > max_price_cents:
        raise ValueError("min_price_cents cannot exceed max_price_cents")

    conditions: list[str] = []
    parameters: list[object] = []
    if available_only:
        conditions.extend(("p.status = ?", "p.stock_quantity > ?"))
        parameters.extend(("active", 0))
    if query:
        conditions.append("(p.name LIKE ? ESCAPE '\\' OR p.description LIKE ? ESCAPE '\\')")
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        parameters.extend((pattern, pattern))
    if category:
        conditions.append("p.category = ? COLLATE NOCASE")
        parameters.append(category)
    if active_promotion is not None:
        conditions.append(
            "p.discount_basis_points IS " + ("NOT NULL" if active_promotion else "NULL")
        )
    if min_price_cents is not None:
        conditions.append("p.effective_price_cents >= ?")
        parameters.append(min_price_cents)
    if max_price_cents is not None:
        conditions.append("p.effective_price_cents <= ?")
        parameters.append(max_price_cents)
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        WITH catalog AS (
            SELECT p.product_id, p.name, c.name AS category, p.price_cents,
                   p.stock_quantity, p.status, p.description, p.specs,
                   MAX(CASE WHEN pr.is_active = 1 THEN pr.discount_basis_points END)
                       AS discount_basis_points,
                   (p.price_cents * (10000 - COALESCE(
                       MAX(CASE WHEN pr.is_active = 1 THEN pr.discount_basis_points END), 0
                   )) + 5000) / 10000 AS effective_price_cents
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN promotions pr ON pr.product_id = p.product_id
            GROUP BY p.product_id, p.name, c.name, p.price_cents,
                     p.stock_quantity, p.status, p.description, p.specs
        )
        SELECT p.product_id, p.name, p.category, p.price_cents,
               p.stock_quantity, p.status, p.description, p.specs,
               p.discount_basis_points, p.effective_price_cents
        FROM catalog p
        {where_clause}
        ORDER BY p.name COLLATE NOCASE, p.product_id
        LIMIT ?
    """
    parameters.append(limit)
    _record_sql(sql, parameters)
    with closing(_open_readonly(db_path)) as connection:
        rows = connection.execute(sql, parameters).fetchall()

    products = []
    for row in rows:
        basis_points = row["discount_basis_points"]
        discount_percent = None
        promotional_price_cents = None
        if basis_points is not None:
            discount_percent = Decimal(basis_points) / Decimal(100)
            promotional_price_cents = int(
                (Decimal(row["price_cents"]) * (Decimal(10000 - basis_points) / Decimal(10000)))
                .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        products.append(
            ProductSummary(
                product_id=row["product_id"],
                name=row["name"],
                category=row["category"],
                price_cents=row["price_cents"],
                stock_quantity=row["stock_quantity"],
                status=row["status"],
                description=row["description"],
                specs=json.loads(row["specs"]),
                promotion_discount_percent=discount_percent,
                promotional_price_cents=promotional_price_cents,
            )
        )
    return products


def get_owned_order(db_path: Path, order_id: str, identity: DemoIdentity) -> OrderSummary | None:
    """Return an order only when it belongs to the backend-provided demo identity."""
    sql = """
        SELECT o.order_id, o.order_date, o.status, o.total_cents, o.payment_method,
               o.tracking_code, o.estimated_delivery, p.name AS product_name,
               oi.quantity
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE o.order_id = ? AND o.customer_id = ?
        ORDER BY p.name COLLATE NOCASE
    """
    _record_sql(sql, (order_id, identity.customer_id), private=True)
    with closing(_open_readonly(db_path)) as connection:
        rows = connection.execute(sql, (order_id, identity.customer_id)).fetchall()
    if not rows:
        return None
    first = rows[0]
    return OrderSummary(
        order_id=first["order_id"],
        order_date=first["order_date"],
        status=first["status"],
        total_cents=first["total_cents"],
        payment_method=first["payment_method"],
        tracking_code=first["tracking_code"],
        estimated_delivery=first["estimated_delivery"],
        items=tuple(
            OrderItemSummary(product_name=row["product_name"], quantity=row["quantity"])
            for row in rows
            if row["product_name"] is not None
        ),
    )
