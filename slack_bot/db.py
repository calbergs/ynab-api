"""
Postgres queries for YNAB transactions. Amounts are returned in dollars (YNAB stores milliunits).
"""
import json
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import TABLE_NAME, get_pg_config


@contextmanager
def get_conn():
    cfg = get_pg_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
    )
    try:
        yield conn
    finally:
        conn.close()


def _run_query(sql: str, params: tuple = ()):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def spending_by_category(start_date: str, end_date: str, category_filter: Optional[str] = None):
    """Sum of spending (outflows) by category. Amounts in dollars. Inflows excluded unless asked."""
    sql = f"""
        SELECT category_name,
               SUM(amount) / 1000.0 AS total_dollars,
               COUNT(*) AS transaction_count
        FROM {TABLE_NAME}
        WHERE date BETWEEN %s AND %s
          AND (deleted IS NULL OR deleted = false)
    """
    params = [start_date, end_date]
    if category_filter:
        sql += " AND category_name ILIKE %s"
        params.append(f"%{category_filter}%")
    sql += " GROUP BY category_name ORDER BY total_dollars ASC"
    rows = _run_query(sql, tuple(params))
    return [dict(r) for r in rows]


def spending_by_payee(start_date: str, end_date: str, payee_filter: Optional[str] = None, limit: int = 30):
    """Sum of spending by payee. Amounts in dollars."""
    sql = f"""
        SELECT payee_name,
               SUM(amount) / 1000.0 AS total_dollars,
               COUNT(*) AS transaction_count
        FROM {TABLE_NAME}
        WHERE date BETWEEN %s AND %s
          AND (deleted IS NULL OR deleted = false)
          AND payee_name IS NOT NULL AND payee_name != ''
    """
    params = [start_date, end_date]
    if payee_filter:
        sql += " AND payee_name ILIKE %s"
        params.append(f"%{payee_filter}%")
    sql += " GROUP BY payee_name ORDER BY total_dollars ASC LIMIT %s"
    params.append(limit)
    rows = _run_query(sql, tuple(params))
    return [dict(r) for r in rows]


def total_spending(start_date: str, end_date: str):
    """Total spending (sum of amount) in the date range. Negative = outflows, positive = inflows. In dollars."""
    sql = f"""
        SELECT SUM(amount) / 1000.0 AS total_dollars,
               COUNT(*) AS transaction_count
        FROM {TABLE_NAME}
        WHERE date BETWEEN %s AND %s
          AND (deleted IS NULL OR deleted = false)
    """
    rows = _run_query(sql, (start_date, end_date))
    return dict(rows[0]) if rows else {"total_dollars": None, "transaction_count": 0}


def recent_transactions(start_date: str, end_date: str, limit: int = 20, category: Optional[str] = None):
    """List recent transactions with date, payee, category, amount (dollars)."""
    sql = f"""
        SELECT date, payee_name, category_name, amount / 1000.0 AS amount_dollars, memo
        FROM {TABLE_NAME}
        WHERE date BETWEEN %s AND %s
          AND (deleted IS NULL OR deleted = false)
    """
    params = [start_date, end_date]
    if category:
        sql += " AND category_name ILIKE %s"
        params.append(f"%{category}%")
    sql += " ORDER BY date DESC, id LIMIT %s"
    params.append(limit)
    rows = _run_query(sql, tuple(params))
    return [dict(r) for r in rows]


def date_range_available():
    """Earliest and latest transaction dates in the DB."""
    sql = f"SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM {TABLE_NAME}"
    rows = _run_query(sql)
    return dict(rows[0]) if rows else {}


def run_tool(name: str, **kwargs) -> str:
    """Execute a named query tool and return JSON string for Claude."""
    try:
        if name == "spending_by_category":
            out = spending_by_category(
                kwargs["start_date"],
                kwargs["end_date"],
                kwargs.get("category_filter"),
            )
        elif name == "spending_by_payee":
            out = spending_by_payee(
                kwargs["start_date"],
                kwargs["end_date"],
                kwargs.get("payee_filter"),
                kwargs.get("limit", 30),
            )
        elif name == "total_spending":
            out = total_spending(kwargs["start_date"], kwargs["end_date"])
        elif name == "recent_transactions":
            out = recent_transactions(
                kwargs["start_date"],
                kwargs["end_date"],
                kwargs.get("limit", 20),
                kwargs.get("category"),
            )
        elif name == "date_range_available":
            out = date_range_available()
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
        return json.dumps(out, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
