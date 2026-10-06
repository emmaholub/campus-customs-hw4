"""Grounded, parameterized catalogue tools for the Campus Customs assistant."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
try:
    from .models import ProductCard, ProductInfo, SearchResult, StockResult
except ImportError:
    from models import ProductCard, ProductInfo, SearchResult, StockResult

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs.db"
AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"


def audit_event(tool_name: str, args: dict, result: str, stop_reason: str) -> None:
    """Append one compact JSON record; this file is JSON Lines by design."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "tool_name": tool_name, "args": args, "result": result[:500], "stop_reason": stop_reason}
    with AUDIT_PATH.open("a", encoding="utf-8") as audit:
        audit.write(json.dumps(record, ensure_ascii=True) + "\n")


def _db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _card(row):
    return ProductCard(product_id=row["product_id"], name=row["name"], price=row["price"], description=row["description"], image_url="/images/" + Path(row["image_file_path"]).name)


def find_products(query: str, limit: int = 6) -> SearchResult:
    """Find catalogue products by garment type, name, description, or search tag."""
    term = f"%{query.strip()}%"
    with _db() as connection:
        rows = connection.execute("SELECT * FROM catalogue WHERE name LIKE ? OR garment_type LIKE ? OR description LIKE ? OR search_tags LIKE ? ORDER BY name LIMIT ?", (term, term, term, term, min(max(limit, 1), 12))).fetchall()
    result = SearchResult(matches=[_card(row) for row in rows])
    audit_event("find_products", {"query": query[:120], "limit": limit}, f"{len(result.matches)} product matches", "tool completed")
    return result


def product_info(product_id_or_name: str) -> ProductInfo | None:
    """Return verified description, price, and total/size availability for one product."""
    with _db() as connection:
        row = connection.execute("SELECT * FROM catalogue WHERE product_id = ? OR lower(name) = lower(?) LIMIT 1", (product_id_or_name, product_id_or_name)).fetchone()
        if not row: return None
        stock = connection.execute("SELECT size, quantity FROM inventory WHERE product_id = ? AND quantity > 0", (row["product_id"],)).fetchall()
    result = ProductInfo(product_id=row["product_id"], name=row["name"], description=row["description"], price=row["price"], available_sizes=[item["size"] for item in stock], stock_total=sum(item["quantity"] for item in stock))
    audit_event("product_info", {"product_id_or_name": product_id_or_name[:120]}, f"price={result.price}; sizes={result.available_sizes}", "tool completed")
    return result


def product_stock(product_id_or_name: str, size: str | None = None) -> StockResult | None:
    """Return verified stock and clearly identify a requested size that is unavailable."""
    with _db() as connection:
        row = connection.execute("SELECT product_id, name FROM catalogue WHERE product_id = ? OR lower(name) = lower(?) LIMIT 1", (product_id_or_name, product_id_or_name)).fetchone()
        if not row: return None
        rows = connection.execute("SELECT size, quantity FROM inventory WHERE product_id = ?", (row["product_id"],)).fetchall()
    requested = next((item["quantity"] for item in rows if size and item["size"].lower() == size.lower()), None)
    available = [item["size"] for item in rows if item["quantity"] > 0]
    result = StockResult(product_id=row["product_id"], product_name=row["name"], requested_size=size, available_sizes=available, quantity=requested or 0, in_stock=(requested > 0 if size else bool(available)))
    audit_event("product_stock", {"product_id_or_name": product_id_or_name[:120], "size": (size or "")[:20]}, f"in_stock={result.in_stock}; quantity={result.quantity}; sizes={result.available_sizes}", "tool completed")
    return result
