"""
Business Logic Engine
─────────────────────
Classifies every raw_edw row into:
  • Custom type  : Combo | LG | DG | Other Model
  • Activation   : New Installation | Reactivation | Different Device Used

Rules (from user):
  COMBO  – CPE ends with "CPE"             (HIGH PRIORITY)
  LG     – CPE starts with "48"
  DG     – CPE starts with "21"
  Other  – everything else

  New Installation     – Karama ID + serial (CPE/ONT) + date are all new
  Reactivation         – Same Karama ID + same serial, different date
  Different Device     – Same Karama ID, different serial, different date
"""

import sqlite3
from database import get_connection


# ──────────────────────────────────────────────
# Device / Custom type classification
# ──────────────────────────────────────────────

def classify_custom(cpe: str | None) -> str:
    """Determine Custom type from CPE serial number."""
    if not cpe:
        return "Other Model"
    cpe = str(cpe).strip()
    if cpe.upper().endswith("CPE"):
        return "Combo"
    if cpe.startswith("48"):
        return "LG"
    if cpe.startswith("21"):
        return "DG"
    return "Other Model"


# ──────────────────────────────────────────────
# Activation type classification
# ──────────────────────────────────────────────

def classify_activation(karama_id, cpe, ont, date_, seen: dict) -> str:
    """
    Classify activation type based on historical context.

    `seen` is a dict keyed by karama_id holding previous records:
        { karama_id: [(cpe, ont, date_), ...] }
    """
    kid = str(karama_id).strip() if karama_id else None
    cpe = str(cpe).strip() if cpe else ""
    ont = str(ont).strip() if ont else ""
    date_ = str(date_).strip() if date_ else ""

    if not kid or kid.lower() in ("none", ""):
        # No karama — treat as new
        return "New Installation"

    if kid not in seen:
        # Completely new karama
        seen[kid] = [(cpe, ont, date_)]
        return "New Installation"

    # Karama exists — check previous records
    for prev_cpe, prev_ont, prev_date in seen[kid]:
        same_serials = (cpe == prev_cpe) and (ont == prev_ont)
        diff_date = (date_ != prev_date)

        if same_serials and diff_date:
            seen[kid].append((cpe, ont, date_))
            return "Reactivation"

    # Karama exists but serials are different
    seen[kid].append((cpe, ont, date_))
    return "Different Device Used"


# ──────────────────────────────────────────────
# Month helpers
# ──────────────────────────────────────────────

MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _parse_date_parts(date_str):
    """Return (year, month_num, month_name) from an ISO date string."""
    try:
        parts = str(date_str).split("-")
        year = parts[0]
        month_num = int(parts[1])
        month_name = MONTH_MAP.get(month_num, "")
        return year, month_num, month_name
    except Exception:
        return None, None, None


# ──────────────────────────────────────────────
# Process all raw_edw → processed_data
# ──────────────────────────────────────────────

def process_all():
    """
    Read every row from raw_edw (+ service_dump for history),
    classify, and insert into processed_data.
    Clears processed_data first for a clean rebuild.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Clear existing processed data
    cur.execute("DELETE FROM processed_data")
    conn.commit()

    # Build history from service_dump first
    seen: dict[str, list] = {}
    cur.execute("SELECT kid, cpe, ont, date_ FROM service_dump WHERE kid IS NOT NULL AND kid != ''")
    for row in cur.fetchall():
        kid = str(row[0]).strip()
        cpe = str(row[1]).strip() if row[1] else ""
        ont = str(row[2]).strip() if row[2] else ""
        date_ = str(row[3]).strip() if row[3] else ""
        if kid and kid.lower() not in ("none", ""):
            seen.setdefault(kid, []).append((cpe, ont, date_))

    # Process raw_edw rows (ordered by date)
    cur.execute("""
        SELECT karama_id, msisdn, new_cpe, new_ont, date_,
               area_name, city, service_plan, customer_type,
               customer_segment, market_type_cd, service_plan_price
        FROM raw_edw
        ORDER BY date_ ASC
    """)
    raw_rows = cur.fetchall()

    batch = []
    for row in raw_rows:
        kid = row[0]
        msisdn = row[1]
        cpe = row[2]
        ont = row[3]
        date_ = row[4]
        area_name = row[5]
        city_val = row[6]
        service_plan = row[7]
        customer_type = row[8]
        customer_segment = row[9]
        market_type_cd = row[10]
        service_plan_price = row[11]

        custom = classify_custom(cpe)
        activation = classify_activation(kid, cpe, ont, date_, seen)

        # CPE Combine = CPE + "," + KID (matching Query.xlsx pattern)
        cpe_str = str(cpe) if cpe else ""
        kid_str = str(kid) if kid else ""
        cpe_combine = f"{cpe_str},{kid_str}" if cpe_str else ""

        year, month_num, month_name = _parse_date_parts(date_)

        batch.append((
            kid_str, str(msisdn) if msisdn else None,
            cpe_str, str(ont) if ont else None,
            date_, cpe_combine, custom, activation,
            year, month_name, month_num,
            area_name, city_val, service_plan,
            customer_type, customer_segment, market_type_cd,
            service_plan_price, "raw_edw",
        ))

    cur.executemany("""
        INSERT INTO processed_data (
            karama_id, msisdn, cpe, ont, date_, cpe_combine, custom, activation_type,
            year, month, month_num, area_name, city, service_plan,
            customer_type, customer_segment, market_type_cd,
            service_plan_price, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "processed": len(batch),
        "message": f"Processed {len(batch)} records through business logic.",
    }


def get_summary() -> dict:
    """Quick summary stats for the sidebar (aligned to Power BI last-6-month scope)."""
    conn = get_connection()
    cur = conn.cursor()

    stats = {}
    cur.execute("""
        SELECT DISTINCT year, month, month_num
        FROM processed_data
        WHERE year IS NOT NULL AND month IS NOT NULL
        ORDER BY CAST(year AS INTEGER) DESC, month_num DESC
        LIMIT 6
    """)
    periods = cur.fetchall()
    if not periods:
        conn.close()
        return {
            "total_records": 0,
            "by_custom": {},
            "by_activation": {},
            "monthly": [],
            "scope": "last_6_months",
        }

    cond = " OR ".join(["(year = ? AND month = ? AND month_num = ?)"] * len(periods))
    params = []
    for y, m, mn in periods:
        params.extend([y, m, mn])

    cur.execute(f"SELECT COUNT(*) FROM processed_data WHERE {cond}", params)
    stats["total_records"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT custom, COUNT(*) as cnt
        FROM processed_data
        WHERE {cond}
        GROUP BY custom
        ORDER BY cnt DESC
    """, params)
    stats["by_custom"] = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(f"""
        SELECT activation_type, COUNT(*) as cnt
        FROM processed_data
        WHERE {cond}
        GROUP BY activation_type
        ORDER BY cnt DESC
    """, params)
    stats["by_activation"] = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(f"""
        SELECT year, month, month_num, COUNT(*) as total,
               SUM(CASE WHEN custom = 'Combo' THEN 1 ELSE 0 END) as combo_count,
               SUM(CASE WHEN activation_type = 'Reactivation' THEN 1 ELSE 0 END) as reactivation_count
        FROM processed_data
        WHERE {cond}
        GROUP BY year, month, month_num
        ORDER BY CAST(year AS INTEGER), month_num
    """, params)
    stats["monthly"] = [
        {
            "year": r[0], "month": r[1], "month_num": r[2],
            "total": r[3], "combo": r[4], "reactivation": r[5],
            "combo_pct": round(r[4]/r[3]*100, 1) if r[3] else 0,
            "reactivation_pct": round(r[5]/r[3]*100, 1) if r[3] else 0,
        }
        for r in cur.fetchall()
    ]
    stats["scope"] = "last_6_months"

    conn.close()
    return stats
