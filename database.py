"""
Database layer – SQLite setup, table creation, Excel import helpers.
"""

import sqlite3
import os
import pandas as pd
from config import DATABASE_PATH

# ──────────────────────────────────────────────
# Connection helper
# ──────────────────────────────────────────────

def get_connection():
    """Return a new SQLite connection with row-factory enabled."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Raw EDW data (as-is from the Excel)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_edw (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date_           TEXT,
            msisdn          TEXT,
            customer_type   TEXT,
            customer_id     TEXT,
            customer_segment TEXT,
            movement_category TEXT,
            movement_minor_category TEXT,
            group_id        TEXT,
            account_name    TEXT,
            parent_account_name TEXT,
            agent_code      TEXT,
            parent_agent_code TEXT,
            fixed_agent_id  TEXT,
            parent_fixed_agent_id TEXT,
            am_name         TEXT,
            parent_am_name  TEXT,
            vertical        TEXT,
            parent_vertical TEXT,
            oppty_number    TEXT,
            market_type_cd  TEXT,
            reporting_date  TEXT,
            old_status      TEXT,
            cal_arpu        TEXT,
            reported_points TEXT,
            service_plan_price REAL,
            service_plan    TEXT,
            paid_addons     TEXT,
            addon_price     REAL,
            commitment_value REAL,
            cust_account_created_date TEXT,
            karama_id       TEXT,
            area_name       TEXT,
            equip_building  TEXT,
            address_name    TEXT,
            city            TEXT,
            order_num       TEXT,
            agent_id        TEXT,
            month           TEXT,
            new_ont         TEXT,
            new_cpe         TEXT,
            import_batch    TEXT
        )
    """)

    # Service dump (historical device reference)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_dump (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            msisdn  TEXT,
            cpe     TEXT,
            ont     TEXT,
            kid     TEXT,
            date_   TEXT,
            import_batch TEXT
        )
    """)

    # Processed / classified data (the "Query" output)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_data (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            karama_id       TEXT,
            msisdn          TEXT,
            cpe             TEXT,
            ont             TEXT,
            date_           TEXT,
            cpe_combine     TEXT,
            custom          TEXT,
            activation_type TEXT,
            year            TEXT,
            month           TEXT,
            month_num       INTEGER,
            area_name       TEXT,
            city            TEXT,
            service_plan    TEXT,
            customer_type   TEXT,
            customer_segment TEXT,
            market_type_cd  TEXT,
            service_plan_price REAL,
            source          TEXT
        )
    """)

    # Track import history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT,
            imported_at TEXT DEFAULT (datetime('now')),
            row_count   INTEGER,
            table_name  TEXT,
            status      TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tables initialised.")


# ──────────────────────────────────────────────
# Import helpers
# ──────────────────────────────────────────────

def _already_imported(filename: str, table_name: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM import_log WHERE filename = ? AND table_name = ? AND status = 'success' LIMIT 1",
        (filename, table_name),
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def import_raw_edw(filepath: str, force: bool = False) -> dict:
    """Import a Raw-EDW Excel file into the raw_edw table."""
    filename = os.path.basename(filepath)
    if not force and _already_imported(filename, "raw_edw"):
        return {"status": "skipped", "message": f"'{filename}' already imported."}

    try:
        df = pd.read_excel(filepath, engine="openpyxl")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # Normalise column names
    col_map = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    # Convert dates to ISO strings
    for col in df.columns:
        if "date" in col:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    expected_cols = [
        "date_", "msisdn", "customer_type", "customer_id", "customer_segment",
        "movement_category", "movement_minor_category", "group_id", "account_name",
        "parent_account_name", "agent_code", "parent_agent_code", "fixed_agent_id",
        "parent_fixed_agent_id", "am_name", "parent_am_name", "vertical",
        "parent_vertical", "oppty_number", "market_type_cd", "reporting_date",
        "old_status", "cal_arpu", "reported_points", "service_plan_price",
        "service_plan", "paid_addons", "addon_price", "commitment_value",
        "cust_account_created_date", "karama_id", "area_name", "equip_building",
        "address_name", "city", "order_num", "agent_id", "month", "new_ont", "new_cpe",
    ]

    # Add missing columns
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    df["import_batch"] = filename
    df = df[[*expected_cols, "import_batch"]]

    # Cast everything to string-safe types
    df = df.astype(object).where(df.notna(), None)

    conn = get_connection()
    rows = df.to_dict("records")
    cur = conn.cursor()
    for row in rows:
        cur.execute(
            f"INSERT INTO raw_edw ({', '.join(row.keys())}) VALUES ({', '.join(['?']*len(row))})",
            list(row.values()),
        )
    conn.commit()

    # Log import
    cur.execute(
        "INSERT INTO import_log (filename, row_count, table_name, status) VALUES (?, ?, ?, ?)",
        (filename, len(rows), "raw_edw", "success"),
    )
    conn.commit()
    conn.close()

    return {"status": "success", "message": f"Imported {len(rows)} rows from '{filename}'.", "row_count": len(rows)}


def import_service_dump(filepath: str, force: bool = False) -> dict:
    """Import a Service Dump Excel file into the service_dump table."""
    filename = os.path.basename(filepath)
    if not force and _already_imported(filename, "service_dump"):
        return {"status": "skipped", "message": f"'{filename}' already imported."}

    try:
        df = pd.read_excel(filepath, engine="openpyxl")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    col_map = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    # Standardise column names
    rename_map = {}
    for c in df.columns:
        if "date" in c.lower():
            rename_map[c] = "date_"
        elif c.lower() in ("kid", "karama_id"):
            rename_map[c] = "kid"
    df.rename(columns=rename_map, inplace=True)

    for col in ["msisdn", "cpe", "ont", "kid", "date_"]:
        if col not in df.columns:
            df[col] = None

    if "date_" in df.columns:
        df["date_"] = pd.to_datetime(df["date_"], errors="coerce").dt.strftime("%Y-%m-%d")

    df["import_batch"] = filename
    df = df[["msisdn", "cpe", "ont", "kid", "date_", "import_batch"]]
    df = df.astype(object).where(df.notna(), None)

    conn = get_connection()
    rows = df.to_dict("records")
    cur = conn.cursor()
    for row in rows:
        cur.execute(
            f"INSERT INTO service_dump ({', '.join(row.keys())}) VALUES ({', '.join(['?']*len(row))})",
            list(row.values()),
        )
    conn.commit()

    cur.execute(
        "INSERT INTO import_log (filename, row_count, table_name, status) VALUES (?, ?, ?, ?)",
        (filename, len(rows), "service_dump", "success"),
    )
    conn.commit()
    conn.close()

    return {"status": "success", "message": f"Imported {len(rows)} rows from '{filename}'.", "row_count": len(rows)}


def run_query(sql: str, params: tuple = ()) -> list:
    """Execute a SELECT query and return list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        conn.close()
        raise e
    conn.close()
    return rows


def get_table_info() -> dict:
    """Return schema info for all tables – used by Gemini for context."""
    conn = get_connection()
    cur = conn.cursor()
    info = {}
    for table in ["raw_edw", "service_dump", "processed_data"]:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [{"name": r[1], "type": r[2]} for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        info[table] = {"columns": cols, "row_count": count}
    conn.close()
    return info


def get_sample_data(table: str, limit: int = 3) -> list:
    """Return a few sample rows from a table."""
    return run_query(f"SELECT * FROM {table} LIMIT ?", (limit,))
