"""
Smart Data Assistant - Main Flask Application
===============================================
A local AI-powered chatbot for telecom activation data analysis.

Usage:
  1. Set your Gemini API key:   set GEMINI_API_KEY=your_key_here
  2. Run:                       python app.py
  3. Open browser:              http://127.0.0.1:5000
  4. Drop new Excel files into: watch_folder/
"""

import os
import re
from flask import Flask, render_template, request, jsonify
from config import SECRET_KEY, DEBUG, HOST, PORT, EXPORTS_FOLDER
from database import init_db, get_table_info, run_query
from business_logic import process_all, get_summary
from gemini_handler import ask_gemini
from file_watcher import start_watcher, get_recent_events
from report_generator import generate_monthly_report, generate_custom_report

# ──────────────────────────────────────────────
# Flask App
# ──────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Initialize DB and folders when gunicorn imports this module
import os as _os
from database import init_db as _init_db
_init_db()
_os.makedirs(EXPORTS_FOLDER, exist_ok=True)

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ──────────────────────────────────────────────
# Pre-built queries for Quick Actions (no AI needed)
# ──────────────────────────────────────────────

PREBUILT_QUERIES = {
    "show me this month's report": {
        "sql": """
            SELECT year as report_year,
                   month as report_month,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_installation,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation,
                   SUM(CASE WHEN activation_type='Different Device Used' THEN 1 ELSE 0 END) as different_device,
                   SUM(CASE WHEN custom='Combo' THEN 1 ELSE 0 END) as combo,
                   SUM(CASE WHEN custom='LG' THEN 1 ELSE 0 END) as lg,
                   SUM(CASE WHEN custom='DG' THEN 1 ELSE 0 END) as dg,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as combo_reactivation_pct
            FROM processed_data
            WHERE year IS NOT NULL
            GROUP BY year, month, month_num
            ORDER BY CAST(year AS INTEGER), month_num
        """,
        "explanation": "Monthly performance report with activation split and COMBO focus metrics",
        "response_type": "table",
    },
    "show combo reactivation trend by month": {
        "sql": """
            SELECT year || ' ' || month as period,
                   COUNT(*) as total,
                   SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) as combo_reactivation,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as combo_reactivation_pct
            FROM processed_data WHERE year IS NOT NULL
            GROUP BY year, month, month_num ORDER BY year, month_num
        """,
        "explanation": "COMBO reactivation trend across all months",
        "response_type": "chart",
        "chart_config": {"type": "line", "title": "COMBO Reactivation Trend", "x_label": "Month", "y_label": "Count", "special": "combo_trend"},
    },
    "show total activations by custom type and activation type": {
        "sql": """
            SELECT custom as device_type, activation_type, COUNT(*) as total
            FROM processed_data
            GROUP BY custom, activation_type
            ORDER BY custom, activation_type
        """,
        "explanation": "Activation breakdown by device type (Combo/LG/DG) and activation type (New/Reactivation/Different Device)",
        "response_type": "table",
    },
    "show top 10 areas by total activations": {
        "sql": """
            SELECT area_name, COUNT(*) as total,
                   SUM(CASE WHEN custom='Combo' THEN 1 ELSE 0 END) as combo,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_install,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation
            FROM processed_data WHERE area_name IS NOT NULL
            GROUP BY area_name ORDER BY total DESC LIMIT 10
        """,
        "explanation": "Top 10 areas ranked by total activations",
        "response_type": "table",
    },
    "i want power bi report": {
        "sql": """
            WITH last_6_months AS (
                SELECT year, month, month_num
                FROM (
                    SELECT DISTINCT year, month, month_num
                    FROM processed_data
                    WHERE year IS NOT NULL AND month IS NOT NULL
                    ORDER BY CAST(year AS INTEGER) DESC, month_num DESC
                    LIMIT 6
                )
            )
            SELECT p.year, p.month,
                   COUNT(*) as total,
                   SUM(CASE WHEN p.activation_type='New Installation' THEN 1 ELSE 0 END) as new_installation,
                   SUM(CASE WHEN p.activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation,
                   SUM(CASE WHEN p.activation_type='Different Device Used' THEN 1 ELSE 0 END) as different_device,
                   SUM(CASE WHEN p.custom='Combo' THEN 1 ELSE 0 END) as combo,
                   SUM(CASE WHEN p.custom='LG' THEN 1 ELSE 0 END) as lg,
                   SUM(CASE WHEN p.custom='DG' THEN 1 ELSE 0 END) as dg
            FROM processed_data p
            WHERE EXISTS (
                SELECT 1 FROM last_6_months l
                WHERE l.year = p.year AND l.month = p.month AND l.month_num = p.month_num
            )
            GROUP BY p.year, p.month, p.month_num
            ORDER BY CAST(p.year AS INTEGER), p.month_num
        """,
        "explanation": "Power BI export (last 6 months) - comprehensive summary ready for download",
        "response_type": "download",
    },
    "show monthly summary with combo reactivation percentage": {
        "sql": """
            WITH last_6_months AS (
                SELECT year, month, month_num
                FROM (
                    SELECT DISTINCT year, month, month_num
                    FROM processed_data
                    WHERE year IS NOT NULL AND month IS NOT NULL
                    ORDER BY CAST(year AS INTEGER) DESC, month_num DESC
                    LIMIT 6
                )
            )
            SELECT p.year, p.month,
                   COUNT(*) as total_activation,
                   SUM(CASE WHEN p.custom='Combo' AND p.activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation_combo,
                   ROUND(CAST(SUM(CASE WHEN p.custom='Combo' AND p.activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as reactivation_combo_pct
            FROM processed_data p
            WHERE EXISTS (
                SELECT 1 FROM last_6_months l
                WHERE l.year = p.year AND l.month = p.month AND l.month_num = p.month_num
            )
            GROUP BY p.year, p.month, p.month_num
            ORDER BY CAST(p.year AS INTEGER), p.month_num
        """,
        "explanation": "Last 6 months summary showing COMBO reactivation count and percentage",
        "response_type": "table",
    },
    "i want april month report": {
        "sql": """
            SELECT year as report_year,
                   month as report_month,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_installation,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation,
                   SUM(CASE WHEN activation_type='Different Device Used' THEN 1 ELSE 0 END) as different_device,
                   SUM(CASE WHEN custom='Combo' THEN 1 ELSE 0 END) as combo,
                   SUM(CASE WHEN custom='LG' THEN 1 ELSE 0 END) as lg,
                   SUM(CASE WHEN custom='DG' THEN 1 ELSE 0 END) as dg,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as combo_reactivation_pct
            FROM processed_data WHERE month = 'Apr'
            GROUP BY year, month, month_num
            ORDER BY CAST(year AS INTEGER), month_num
        """,
        "explanation": "April monthly report with clear activation split and COMBO metrics",
        "response_type": "table",
    },
    "show me combo details": {
        "sql": """
            SELECT year, month, activation_type, COUNT(*) as total
            FROM processed_data WHERE custom = 'Combo'
            GROUP BY year, month, month_num, activation_type
            ORDER BY year, month_num, activation_type
        """,
        "explanation": "COMBO device details broken down by month and activation type",
        "response_type": "table",
    },
    "show combo activation split": {
        "sql": """
            SELECT activation_type, COUNT(*) as total
            FROM processed_data
            WHERE custom = 'Combo'
              AND activation_type IN ('Reactivation', 'New Installation', 'Different Device Used')
            GROUP BY activation_type
            ORDER BY CASE activation_type
                WHEN 'Reactivation' THEN 1
                WHEN 'New Installation' THEN 2
                WHEN 'Different Device Used' THEN 3
                ELSE 4
            END
        """,
        "explanation": "COMBO activation split for Reactivation, New Installation, and Different Device Used",
        "response_type": "table",
    },
    "what is the reactivation trend?": {
        "sql": """
            SELECT year || ' ' || month as period,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_installation,
                   ROUND(CAST(SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as reactivation_pct
            FROM processed_data WHERE year IS NOT NULL
            GROUP BY year, month, month_num ORDER BY year, month_num
        """,
        "explanation": "Reactivation trend compared to new installations by month",
        "response_type": "chart",
        "chart_config": {"type": "line", "title": "Reactivation Trend", "x_label": "Month", "y_label": "Count"},
    },
    "compare lg vs dg activations by month": {
        "sql": """
            SELECT year || ' ' || month as period,
                   SUM(CASE WHEN custom='LG' THEN 1 ELSE 0 END) as LG,
                   SUM(CASE WHEN custom='DG' THEN 1 ELSE 0 END) as DG
            FROM processed_data WHERE year IS NOT NULL
            GROUP BY year, month, month_num ORDER BY year, month_num
        """,
        "explanation": "LG vs DG activation comparison by month",
        "response_type": "chart",
        "chart_config": {"type": "bar", "title": "LG vs DG Activations", "x_label": "Month", "y_label": "Count"},
    },
    "which area has most new installations?": {
        "sql": """
            SELECT area_name, COUNT(*) as new_installations
            FROM processed_data
            WHERE activation_type = 'New Installation' AND area_name IS NOT NULL
            GROUP BY area_name ORDER BY new_installations DESC LIMIT 15
        """,
        "explanation": "Top 15 areas ranked by new installations",
        "response_type": "table",
    },
}


def _match_prebuilt(question: str):
    """Try to match a user question to a pre-built query."""
    q = question.lower().strip()
    # Exact match
    if q in PREBUILT_QUERIES:
        return PREBUILT_QUERIES[q]
    # Fuzzy match — check if any key is contained in question or vice versa
    for key, val in PREBUILT_QUERIES.items():
        if key in q or q in key:
            return val
    return None


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle a user chat message."""
    data = request.get_json()
    question = data.get('question', '').strip()

    if not question:
        return jsonify({"success": False, "error": "Please enter a question."})

    # Check for download/export intent
    download_file = None
    q_lower = question.lower()

    if any(kw in q_lower for kw in ['download', 'export']):
        month_match = re.search(
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*',
            q_lower
        )
        year_match = re.search(r'(202[0-9])', q_lower)
        month_name = None
        if month_match:
            month_map = {
                'jan': 'Jan', 'feb': 'Feb', 'mar': 'Mar', 'apr': 'Apr',
                'may': 'May', 'jun': 'Jun', 'jul': 'Jul', 'aug': 'Aug',
                'sep': 'Sep', 'oct': 'Oct', 'nov': 'Nov', 'dec': 'Dec',
            }
            month_name = month_map.get(month_match.group(1)[:3])
        year_val = year_match.group(1) if year_match else None
        download_file = generate_monthly_report(year=year_val, month=month_name)

    base64_img = None
    if 'pie' in q_lower and ('python' in q_lower or 'also' in q_lower or 'chart' in q_lower):
        from report_generator import generate_pie_chart_base64
        base64_img = generate_pie_chart_base64()
        
        # If they just asked for a pie chart and nothing else matches prebuilt, we can return early
        if not _match_prebuilt(question):
            return jsonify({
                "success": True,
                "explanation": "Here is the Device Distribution Pie Chart rendered via Matplotlib Python library:",
                "base64_image": base64_img,
                "response_type": "image"
            })

    # Step 1: Try pre-built query (instant, no AI needed)
    prebuilt = _match_prebuilt(question)
    if prebuilt:
        try:
            results = run_query(prebuilt["sql"])
            result = {
                "success": True,
                "sql": prebuilt["sql"].strip(),
                "explanation": prebuilt["explanation"],
                "response_type": prebuilt.get("response_type", "table"),
                "chart_config": prebuilt.get("chart_config"),
                "data": results,
                "row_count": len(results),
            }
        except Exception as e:
            result = {"success": False, "error": f"Query error: {str(e)}"}
    else:
        # Step 2: Ask Gemini AI for custom questions
        result = ask_gemini(question)

    if not result.get('success'):
        return jsonify({
            "success": False,
            "error": result.get('error', 'Failed to process your question.'),
        })

    # Generate download file if needed
    if result.get('response_type') == 'download' and not download_file:
        sql = result.get('sql', '')
        if sql:
            download_file = generate_custom_report(sql, report_name="Custom_Report")

    response = {
        "success": True,
        "explanation": result.get('explanation', ''),
        "data": result.get('data', []),
        "row_count": result.get('row_count', 0),
        "response_type": result.get('response_type', 'table'),
        "chart_config": result.get('chart_config'),
        "sql": result.get('sql', ''),
        "download_file": download_file,
    }

    return jsonify(response)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload an Excel file and import it into the database."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided."})
    file = request.files['file']
    if not file.filename.endswith('.xlsx'):
        return jsonify({"success": False, "error": "Only .xlsx files are supported."})
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    filename = file.filename.lower()
    if 'dump' in filename or 'service' in filename:
        from database import import_service_dump
        result = import_service_dump(tmp_path)
    else:
        from database import import_raw_edw
        result = import_raw_edw(tmp_path)
    os.unlink(tmp_path)
    if result.get('status') == 'success':
        process_all()
    return jsonify(result)


@app.route('/api/stats')
def stats():
    """Return summary stats for the sidebar."""
    try:
        summary = get_summary()
        return jsonify({"success": True, "stats": summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/reprocess', methods=['POST'])
def reprocess():
    """Re-process all raw data through business logic."""
    try:
        result = process_all()
        return jsonify({"success": True, "message": result.get('message', 'Done.')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/watcher-events')
def watcher_events():
    """Return recent file watcher events."""
    return jsonify({"events": get_recent_events()})


@app.route('/api/schema')
def schema():
    """Return database schema (for debugging)."""
    return jsonify(get_table_info())


@app.route('/api/dashboard')
def dashboard():
    """Return all dashboard data for the Power BI-style report."""
    try:
        # Monthly activations
        monthly = run_query("""
            SELECT year || ' ' || month as period, year, month, month_num,
                   COUNT(*) as total,
                   SUM(CASE WHEN custom='Combo' THEN 1 ELSE 0 END) as combo,
                   SUM(CASE WHEN custom='LG' THEN 1 ELSE 0 END) as lg,
                   SUM(CASE WHEN custom='DG' THEN 1 ELSE 0 END) as dg,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_install,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation,
                   SUM(CASE WHEN activation_type='Different Device Used' THEN 1 ELSE 0 END) as diff_device,
                   SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) as combo_reactivation,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as combo_react_pct
            FROM processed_data WHERE year IS NOT NULL
            GROUP BY year, month, month_num ORDER BY year, month_num
        """)

        # Device type distribution
        device_dist = run_query("""
            SELECT custom as type, COUNT(*) as count FROM processed_data GROUP BY custom ORDER BY count DESC
        """)

        # Activation type distribution
        act_dist = run_query("""
            SELECT activation_type as type, COUNT(*) as count FROM processed_data GROUP BY activation_type ORDER BY count DESC
        """)

        # Top 10 areas
        top_areas = run_query("""
            SELECT area_name, COUNT(*) as total FROM processed_data
            WHERE area_name IS NOT NULL AND area_name != ''
            GROUP BY area_name ORDER BY total DESC LIMIT 10
        """)

        # KPIs
        kpis = run_query("""
            SELECT COUNT(*) as total_records,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_installs,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivations,
                   SUM(CASE WHEN custom='Combo' THEN 1 ELSE 0 END) as combos,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 2) as combo_react_pct
            FROM processed_data
        """)

        return jsonify({
            "success": True,
            "monthly": monthly,
            "device_dist": device_dist,
            "activation_dist": act_dist,
            "top_areas": top_areas,
            "kpis": kpis[0] if kpis else {},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/powerbi-dashboard')
def powerbi_dashboard():
    """Render the full-screen Power BI clone dashboard template."""
    return render_template('powerbi_dashboard.html')


@app.route('/api/data', methods=['GET', 'POST'])
def powerbi_dashboard_data():
    """
    Compatibility API for the merged Prabaa Power BI dashboard.
    Returns last-6-month data with optional slicer filters.
    """
    try:
        req = request.get_json(silent=True) or {}
        req_year = str(req.get('year', 'All')).strip()
        req_months = req.get('months') or []
        req_customs = req.get('customs') or []

        activation_types = ['Different Device Used', 'New Installation', 'Reactivation']
        month_full = {
            'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
            'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
            'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December',
        }

        base_cte = """
            WITH last_6_months AS (
                SELECT year, month, month_num
                FROM (
                    SELECT DISTINCT year, month, month_num
                    FROM processed_data
                    WHERE year IS NOT NULL AND month IS NOT NULL
                    ORDER BY CAST(year AS INTEGER) DESC, month_num DESC
                    LIMIT 6
                )
            )
        """

        where_parts = [
            "p.year IS NOT NULL",
            "p.month IS NOT NULL",
            "p.activation_type IN (?, ?, ?)",
            "EXISTS (SELECT 1 FROM last_6_months l WHERE l.year = p.year AND l.month = p.month AND l.month_num = p.month_num)",
        ]
        params = list(activation_types)

        if req_year and req_year.lower() != 'all':
            where_parts.append("p.year = ?")
            params.append(req_year)

        if req_months:
            placeholders = ", ".join(["?"] * len(req_months))
            where_parts.append(f"p.month IN ({placeholders})")
            params.extend(req_months)

        if req_customs:
            placeholders = ", ".join(["?"] * len(req_customs))
            where_parts.append(f"p.custom IN ({placeholders})")
            params.extend(req_customs)

        where_clause = " AND ".join(where_parts)

        total_rows = run_query(
            f"""
            {base_cte}
            SELECT COUNT(*) as total
            FROM processed_data p
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total_activations = int(total_rows[0]['total']) if total_rows else 0
        kpi_text = f"{(total_activations / 1000):.3f}K" if total_activations > 1000 else str(total_activations)

        years_rows = run_query(
            f"""
            {base_cte}
            SELECT DISTINCT p.year
            FROM processed_data p
            WHERE {where_clause}
            ORDER BY CAST(p.year AS INTEGER)
            """,
            tuple(params),
        )
        years = [int(r['year']) for r in years_rows if str(r.get('year', '')).isdigit()]

        months_rows = run_query(
            f"""
            {base_cte}
            SELECT p.year, p.month, p.month_num
            FROM processed_data p
            WHERE {where_clause}
            GROUP BY p.year, p.month, p.month_num
            ORDER BY CAST(p.year AS INTEGER), p.month_num
            """,
            tuple(params),
        )
        months = [month_full.get(r['month'], r['month']) for r in months_rows]

        activation_rows = run_query(
            f"""
            {base_cte}
            SELECT p.activation_type as type, COUNT(*) as cnt
            FROM processed_data p
            WHERE {where_clause}
            GROUP BY p.activation_type
            """,
            tuple(params),
        )
        activation_map = {r['type']: int(r['cnt']) for r in activation_rows}
        activation_table = {
            "Different Device Used": activation_map.get("Different Device Used", 0),
            "New Installation": activation_map.get("New Installation", 0),
            "Reactivation": activation_map.get("Reactivation", 0),
        }

        month_totals_rows = run_query(
            f"""
            {base_cte}
            SELECT p.year, p.month, p.month_num, COUNT(*) as total
            FROM processed_data p
            WHERE {where_clause}
            GROUP BY p.year, p.month, p.month_num
            ORDER BY CAST(p.year AS INTEGER), p.month_num
            """,
            tuple(params),
        )

        monthly_table = []
        chart_labels = []
        for r in month_totals_rows:
            display_month = month_full.get(r['month'], r['month'])
            monthly_table.append({"month": display_month, "total": int(r['total'])})
            chart_labels.append(display_month)

        chart_rows = run_query(
            f"""
            {base_cte}
            SELECT p.year, p.month, p.month_num,
                   SUM(CASE WHEN p.activation_type='Different Device Used' THEN 1 ELSE 0 END) as diff_device,
                   SUM(CASE WHEN p.activation_type='New Installation' THEN 1 ELSE 0 END) as new_install,
                   SUM(CASE WHEN p.activation_type='Reactivation' THEN 1 ELSE 0 END) as react
            FROM processed_data p
            WHERE {where_clause}
            GROUP BY p.year, p.month, p.month_num
            ORDER BY CAST(p.year AS INTEGER), p.month_num
            """,
            tuple(params),
        )

        chart_datasets = {
            "Different Device Used": [int(r['diff_device']) for r in chart_rows],
            "New Installation": [int(r['new_install']) for r in chart_rows],
            "Reactivation": [int(r['react']) for r in chart_rows],
        }

        return jsonify({
            "kpi": kpi_text,
            "raw_total": total_activations,
            "filters": {
                "years": years,
                "months": months,
                "customs": ['Combo', 'DG', 'LG', 'Other Model'],
            },
            "activation_table": activation_table,
            "monthly_table": monthly_table,
            "chart_labels": chart_labels,
            "chart_datasets": chart_datasets,
        })
    except Exception as e:
        return jsonify({
            "kpi": "0",
            "raw_total": 0,
            "filters": {"years": [], "months": [], "customs": ['Combo', 'DG', 'LG', 'Other Model']},
            "activation_table": {
                "Different Device Used": 0,
                "New Installation": 0,
                "Reactivation": 0,
            },
            "monthly_table": [],
            "chart_labels": [],
            "chart_datasets": {
                "Different Device Used": [],
                "New Installation": [],
                "Reactivation": [],
            },
            "warning": f"Backend error: {str(e)}",
        })


@app.route('/api/powerbi-data')
def powerbi_data():
    """Return specific data for the Power BI clone dashboard (last 6 months, specific activation types)."""
    try:
        months_query = """
            SELECT DISTINCT year, month, month_num 
            FROM processed_data 
            WHERE year IS NOT NULL AND month IS NOT NULL 
            ORDER BY year DESC, month_num DESC 
            LIMIT 6
        """
        last_6_months = run_query(months_query)
        if not last_6_months:
             return jsonify({"success": False, "error": "No data found."})
        
        last_6_months.sort(key=lambda x: (x['year'], x['month_num']))
        
        valid_periods = [f"'{r['year']}-{r['month']}'" for r in last_6_months]
        period_filter = f"year || '-' || month IN ({','.join(valid_periods)})"
        act_types = "'Reactivation', 'New Installation', 'Different Device Used'"
        base_where = f"WHERE {period_filter} AND activation_type IN ({act_types})"

        kpis = run_query(f"SELECT COUNT(*) as total_activations FROM processed_data {base_where}")
        
        type_tbl = run_query(f"""
            SELECT activation_type as type, COUNT(*) as count 
            FROM processed_data 
            {base_where}
            GROUP BY activation_type 
            ORDER BY type
        """)

        month_tbl = run_query(f"""
            SELECT month as month_name, COUNT(*) as total 
            FROM processed_data 
            {base_where}
            GROUP BY year, month, month_num 
            ORDER BY year, month_num
        """)

        combo_data = run_query(f"""
            SELECT year || ' ' || month as period, 
                   COUNT(*) as total_activation, 
                   SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) as reactivation_combo,
                   ROUND(CAST(SUM(CASE WHEN custom='Combo' AND activation_type='Reactivation' THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*)*100, 0) as pct
            FROM processed_data 
            {base_where}
            GROUP BY year, month, month_num 
            ORDER BY year, month_num
        """)

        cluster_data = run_query(f"""
            SELECT year, month, month_num,
                   SUM(CASE WHEN activation_type='Different Device Used' THEN 1 ELSE 0 END) as diff_device,
                   SUM(CASE WHEN activation_type='New Installation' THEN 1 ELSE 0 END) as new_install,
                   SUM(CASE WHEN activation_type='Reactivation' THEN 1 ELSE 0 END) as react
            FROM processed_data
            {base_where}
            GROUP BY year, month, month_num
            ORDER BY year, month_num
        """)

        return jsonify({
            "success": True,
            "kpis": kpis[0] if kpis else {},
            "type_table": type_tbl,
            "month_table": month_tbl,
            "combo_chart": combo_data,
            "cluster_chart": cluster_data,
            "metadata": {"months": [r['month'] for r in last_6_months], "year": last_6_months[-1]['year'] }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ──────────────────────────────────────────────
# Initial Data Load
# ──────────────────────────────────────────────

def initial_load():
    """Load the initial Excel files if the database is empty."""
    from database import run_query, import_raw_edw, import_service_dump

    counts = run_query("SELECT COUNT(*) as cnt FROM raw_edw")
    if counts and counts[0]['cnt'] > 0:
        print("[INIT] Database already has data. Skipping initial load.")
        print(f"[INIT] raw_edw: {counts[0]['cnt']} rows")
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(base_dir)

    # Try to find and import the Raw-EDW file
    raw_edw_path = os.path.join(parent_dir, "Raw - EDW New.xlsx")
    if os.path.exists(raw_edw_path):
        print(f"[INIT] Importing Raw-EDW from: {raw_edw_path}")
        result = import_raw_edw(raw_edw_path)
        print(f"[INIT] -> {result}")

    # Try to find and import the Service Dump
    dump_path = os.path.join(parent_dir, "Service Dump Till July-25.xlsx")
    if os.path.exists(dump_path):
        print(f"[INIT] Importing Service Dump from: {dump_path}")
        result = import_service_dump(dump_path)
        print(f"[INIT] -> {result}")

    # Process all data
    print("[INIT] Running business logic on all data...")
    result = process_all()
    print(f"[INIT] -> {result}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 50)
    print("  Smart Data Assistant")
    print("  AI-Powered Telecom Data Chatbot")
    print("=" * 50)

    # Initialise database
    init_db()

    # Load initial data
    initial_load()

    # Start file watcher
    start_watcher()

    # Ensure exports folder exists
    os.makedirs(EXPORTS_FOLDER, exist_ok=True)

    print(f"\n>> Open your browser at: http://{HOST}:{PORT}")
    print(f">> Drop new Excel files into: watch_folder/")
    print(f">> Gemini API configured: {'YES' if os.environ.get('GEMINI_API_KEY') else 'NO - set GEMINI_API_KEY'}")
    print(f">> Groq fallback configured: {'YES' if os.environ.get('GROQ_API_KEY') else 'NO - set GROQ_API_KEY'}")
    print()

    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
