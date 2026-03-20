import requests
import csv
import json
import os
import sys
from datetime import datetime, timedelta, date
import psycopg2
from psycopg2.extras import execute_values
from secrets import (
    YNAB_TOKEN,
    BASE_URL,
    budget_id,
    pg_host,
    pg_port,
    pg_user,
    pg_password,
    dbname,
)

TABLE_NAME = "ynab_transactions"
DAYS_BACK = 14  # default; override via env var DAYS_BACK


def _get_days_back() -> int:
    """
    Allow Airflow/CLI to override the incremental window.
    Use env var DAYS_BACK (int). Falls back to the module default (DAYS_BACK).
    """
    raw = os.getenv("DAYS_BACK")
    if raw is None or str(raw).strip() == "":
        return DAYS_BACK
    try:
        val = int(raw)
        if val < 0:
            raise ValueError("DAYS_BACK must be >= 0")
        return val
    except Exception as e:
        print(f"WARNING: Invalid DAYS_BACK='{raw}' ({e}); using default {DAYS_BACK}")
        return DAYS_BACK

# -----------------------------------------
#  FETCH ALL TRANSACTIONS
# -----------------------------------------
def fetch_all_transactions(budget_id):
    url = f"{BASE_URL}/budgets/{budget_id}/transactions"
    headers = {"Authorization": f"Bearer {YNAB_TOKEN}"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()["data"]["transactions"]

# -----------------------------------------
#  WRITE CSV (ONLY T-DAYS_BACK DAYS, OVERWRITE)
# -----------------------------------------
def write_partitioned_csv(transactions, days_back=None):
    """
    Write CSV files for the last DAYS_BACK days plus today, overwriting existing files.
    Files are overwritten even if there are no transactions for that date.
    """
    days_back = DAYS_BACK if days_back is None else int(days_back)
    today = date.today()
    cutoff = today - timedelta(days=days_back)

    # group transactions by date (only for dates in range)
    partitions = {}
    for t in transactions:
        tx_date = datetime.strptime(t["date"], "%Y-%m-%d").date()
        if cutoff <= tx_date <= today:
            partitions.setdefault(tx_date, []).append(t)

    output_files = []

    # Process all dates from cutoff to today (inclusive) to ensure overwrite
    current_date = cutoff
    while current_date <= today:
        folder = f"data/year={current_date.year}/month={current_date.month:02d}/day={current_date.day:02d}"
        os.makedirs(folder, exist_ok=True)

        file_path = os.path.join(
            folder,
            f"{current_date.year}_{current_date.month:02d}_{current_date.day:02d}.csv"
        )

        # Get transactions for this date (empty list if none)
        rows = partitions.get(current_date, [])
        
        if rows:
            # Write transactions if any exist
            fieldnames = sorted({k for r in rows for k in r.keys()})
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        else:
            # Overwrite with empty file (or just ensure it's overwritten)
            # Create empty file to ensure overwrite
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                pass  # Empty file

        output_files.append(file_path)
        current_date += timedelta(days=1)

    return output_files

# -----------------------------------------
#  POSTGRES FULL REFRESH LOADER
# -----------------------------------------
def normalize_transaction(t: dict) -> dict:
    return {
        k: json.dumps(v) if isinstance(v, (dict, list)) else v
        for k, v in t.items()
    }

def full_refresh_postgres(transactions):
    """
    Upsert transactions from YNAB API into Postgres table.
    Uses UPSERT to preserve historical data that may not be in the API response.
    Returns True on success, False on error.
    """
    try:
        conn = psycopg2.connect(
            host=pg_host,
            dbname=dbname,
            user=pg_user,
            password=pg_password,
            port=pg_port,
        )
        conn.autocommit = False
        cur = conn.cursor()

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id TEXT PRIMARY KEY,
                date DATE,
                amount BIGINT,
                approved BOOLEAN,
                cleared TEXT,
                debt_transaction_type TEXT,
                deleted BOOLEAN,
                flag_color TEXT,
                flag_name TEXT,
                import_id TEXT,
                import_payee_name TEXT,
                import_payee_name_original TEXT,
                matched_transaction_id TEXT,
                memo TEXT,
                payee_id TEXT,
                payee_name TEXT,
                category_id TEXT,
                category_name TEXT,
                account_id TEXT,
                account_name TEXT,
                subtransactions JSONB,
                transfer_account_id TEXT,
                transfer_transaction_id TEXT,
                load_timestamp TIMESTAMPTZ
            );
        """)

        # Use UPSERT to preserve historical data
        # This will insert new transactions or update existing ones
        # Historical data not in the API response will remain untouched
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                id, date, amount, approved, cleared, debt_transaction_type, deleted,
                flag_color, flag_name, import_id, import_payee_name, import_payee_name_original,
                matched_transaction_id, memo, payee_id, payee_name, category_id, category_name,
                account_id, account_name, subtransactions, transfer_account_id,
                transfer_transaction_id, load_timestamp
            )
            VALUES (
                %(id)s, %(date)s, %(amount)s, %(approved)s, %(cleared)s,
                %(debt_transaction_type)s, %(deleted)s, %(flag_color)s, %(flag_name)s,
                %(import_id)s, %(import_payee_name)s, %(import_payee_name_original)s,
                %(matched_transaction_id)s, %(memo)s, %(payee_id)s, %(payee_name)s,
                %(category_id)s, %(category_name)s, %(account_id)s, %(account_name)s,
                %(subtransactions)s, %(transfer_account_id)s,
                %(transfer_transaction_id)s, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                date = EXCLUDED.date,
                amount = EXCLUDED.amount,
                approved = EXCLUDED.approved,
                cleared = EXCLUDED.cleared,
                debt_transaction_type = EXCLUDED.debt_transaction_type,
                deleted = EXCLUDED.deleted,
                flag_color = EXCLUDED.flag_color,
                flag_name = EXCLUDED.flag_name,
                import_id = EXCLUDED.import_id,
                import_payee_name = EXCLUDED.import_payee_name,
                import_payee_name_original = EXCLUDED.import_payee_name_original,
                matched_transaction_id = EXCLUDED.matched_transaction_id,
                memo = EXCLUDED.memo,
                payee_id = EXCLUDED.payee_id,
                payee_name = EXCLUDED.payee_name,
                category_id = EXCLUDED.category_id,
                category_name = EXCLUDED.category_name,
                account_id = EXCLUDED.account_id,
                account_name = EXCLUDED.account_name,
                subtransactions = EXCLUDED.subtransactions,
                transfer_account_id = EXCLUDED.transfer_account_id,
                transfer_transaction_id = EXCLUDED.transfer_transaction_id,
                load_timestamp = NOW();
        """

        for t in transactions:
            cur.execute(insert_sql, normalize_transaction(t))

        cur.close()
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"ERROR: Failed to connect to Postgres database.")
        print(f"  Connection details: {pg_user}@{pg_host}:{pg_port}/{dbname}")
        print(f"  Error: {str(e)}")
        print(f"  Please check:")
        print(f"    - PostgreSQL server is running")
        print(f"    - Database credentials are correct")
        print(f"    - User '{pg_user}' has access to database '{dbname}'")
        return False
    except Exception as e:
        print(f"ERROR: Failed to load data into Postgres: {str(e)}")
        return False


def cleanup_missing_transactions_postgres(api_transactions: list[dict], cutoff_date: date) -> bool:
    """
    For full refresh only:
    Delete rows from Postgres whose `id` is not present in the API response,
    limited to `date >= cutoff_date`.

    Uses a TEMP table of API ids (avoids huge NOT IN lists).
    """
    api_ids = {t.get("id") for t in api_transactions if t.get("id")}
    if not api_ids:
        # Safety: don't let a broken API call wipe your table.
        print("WARNING: API returned 0 transaction ids; skipping cleanup delete step.")
        return True

    try:
        conn = psycopg2.connect(
            host=pg_host,
            dbname=dbname,
            user=pg_user,
            password=pg_password,
            port=pg_port,
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TEMP TABLE tmp_api_transaction_ids (
                id TEXT PRIMARY KEY
            );
            """
        )

        # Bulk insert ids in chunks to avoid parameter/packet limits.
        api_id_list = list(api_ids)
        chunk_size = 5000
        for i in range(0, len(api_id_list), chunk_size):
            chunk = api_id_list[i : i + chunk_size]
            execute_values(
                cur,
                "INSERT INTO tmp_api_transaction_ids (id) VALUES %s ON CONFLICT DO NOTHING",
                [(x,) for x in chunk],
            )

        delete_sql = f"""
            DELETE FROM {TABLE_NAME}
            WHERE date >= %s
              AND id NOT IN (SELECT id FROM tmp_api_transaction_ids);
        """
        cur.execute(delete_sql, (cutoff_date,))

        cur.close()
        conn.commit()
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print("ERROR: Failed to connect to Postgres database for cleanup step.")
        print(f"  Connection details: {pg_user}@{pg_host}:{pg_port}/{dbname}")
        print(f"  Error: {str(e)}")
        return False
    except Exception as e:
        print(f"ERROR: Cleanup delete step failed: {str(e)}")
        return False

# -----------------------------------------
#  MAIN
# -----------------------------------------
def _is_full_refresh():
    """True when FULL_REFRESH env is set to true (e.g. by Airflow DAG config)."""
    return os.getenv("FULL_REFRESH", "false").lower() in ("true", "1", "yes")


if __name__ == "__main__":
    full_refresh = _is_full_refresh()
    days_back = _get_days_back()
    print("Fetching ALL transactions from YNAB API...")
    all_transactions = fetch_all_transactions(budget_id)
    print(f"Fetched {len(all_transactions)} transactions.")

    if full_refresh:
        print("Full refresh cleanup: deleting transactions missing from API response...")
        cutoff_date = date.today() - timedelta(days=days_back)
        cleanup_ok = cleanup_missing_transactions_postgres(all_transactions, cutoff_date=cutoff_date)
        if not cleanup_ok:
            print("Cleanup delete step failed; aborting.")
            sys.exit(1)

        transactions_to_upsert = all_transactions
        print("Full refresh: will upsert ALL transactions to Postgres.")
    else:
        today = date.today()
        cutoff = today - timedelta(days=days_back)
        transactions_to_upsert = [
            t for t in all_transactions
            if datetime.strptime(t["date"], "%Y-%m-%d").date() >= cutoff
        ]
        print(f"Incremental: will upsert only last {days_back} days ({len(transactions_to_upsert)} transactions).")

    print(f"Writing CSVs for last {days_back} days (overwrite)...")
    files = write_partitioned_csv(all_transactions, days_back=days_back)
    print(f"Wrote {len(files)} CSV files.")

    print("Upserting transactions into Postgres...")
    success = full_refresh_postgres(transactions_to_upsert)
    if success:
        print(f"Upserted {len(transactions_to_upsert)} transactions into Postgres.")
        if full_refresh:
            print("(Full refresh: run payee correction task if using Airflow.)")
    else:
        print("Postgres load failed. CSV files were written successfully.")
        sys.exit(1)
