"""
Report Generator
────────────────
Builds downloadable Excel / CSV reports from the database.
"""

import os
import time
import pandas as pd
from database import run_query
from config import EXPORTS_FOLDER


def _ensure_exports_dir():
    os.makedirs(EXPORTS_FOLDER, exist_ok=True)


def generate_monthly_report(year: str = None, month: str = None) -> str:
    """Generate a comprehensive monthly report as Excel. Returns the file path."""
    _ensure_exports_dir()

    where_parts = []
    params = []
    if year:
        where_parts.append("year = ?")
        params.append(year)
    if month:
        where_parts.append("month = ?")
        params.append(month)

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Summary sheet data
    summary_sql = f"""
        SELECT year, month, month_num,
               COUNT(*) as total_activations,
               SUM(CASE WHEN custom = 'Combo' THEN 1 ELSE 0 END) as combo,
               SUM(CASE WHEN custom = 'LG' THEN 1 ELSE 0 END) as lg,
               SUM(CASE WHEN custom = 'DG' THEN 1 ELSE 0 END) as dg,
               SUM(CASE WHEN custom = 'Other Model' THEN 1 ELSE 0 END) as other_model,
               SUM(CASE WHEN activation_type = 'New Installation' THEN 1 ELSE 0 END) as new_installation,
               SUM(CASE WHEN activation_type = 'Reactivation' THEN 1 ELSE 0 END) as reactivation,
               SUM(CASE WHEN activation_type = 'Different Device Used' THEN 1 ELSE 0 END) as different_device,
               ROUND(CAST(SUM(CASE WHEN custom = 'Combo' AND activation_type = 'Reactivation' THEN 1 ELSE 0 END) AS FLOAT)
                     / NULLIF(COUNT(*), 0) * 100, 2) as combo_reactivation_pct
        FROM processed_data
        {where_clause}
        GROUP BY year, month, month_num
        ORDER BY year, month_num
    """

    # Detail sheet data
    detail_sql = f"""
        SELECT karama_id, msisdn, cpe, ont, date_, custom, activation_type,
               area_name, city, service_plan, customer_type, service_plan_price,
               year, month
        FROM processed_data
        {where_clause}
        ORDER BY date_
    """

    summary_data = run_query(summary_sql, tuple(params))
    detail_data = run_query(detail_sql, tuple(params))

    # Build file name
    parts = ["Report"]
    if year:
        parts.append(year)
    if month:
        parts.append(month)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{'_'.join(parts)}_{timestamp}.xlsx"
    filepath = os.path.join(EXPORTS_FOLDER, filename)

    # Write Excel with multiple sheets
    with pd.ExcelWriter(filepath, engine="xlsxwriter") as writer:
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Summary", index=False)

            # Format the summary sheet
            workbook = writer.book
            worksheet = writer.sheets["Summary"]
            header_format = workbook.add_format({
                "bold": True, "bg_color": "#1a1a2e", "font_color": "#e94560",
                "border": 1, "text_wrap": True,
            })
            for col_num, value in enumerate(df_summary.columns):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 18)

        if detail_data:
            df_detail = pd.DataFrame(detail_data)
            df_detail.to_excel(writer, sheet_name="Detail", index=False)

            worksheet = writer.sheets["Detail"]
            header_format = workbook.add_format({
                "bold": True, "bg_color": "#16213e", "font_color": "#0f3460",
                "border": 1,
            })
            for col_num, value in enumerate(df_detail.columns):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 16)

    return filename


def generate_custom_report(sql: str, report_name: str = "Custom_Report") -> str:
    """Generate a report from a custom SQL query. Returns the file path."""
    _ensure_exports_dir()

    data = run_query(sql)
    if not data:
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{report_name}_{timestamp}.xlsx"
    filepath = os.path.join(EXPORTS_FOLDER, filename)

    df = pd.DataFrame(data)
    with pd.ExcelWriter(filepath, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Data", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Data"]
        header_format = workbook.add_format({
            "bold": True, "bg_color": "#1a1a2e", "font_color": "#e94560", "border": 1,
        })
        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 16)

    return filename


import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def generate_powerbi_export() -> str:
    """Generate a comprehensive flat file optimised for Power BI import, including a Python-generated pie chart."""
    _ensure_exports_dir()

    sql = """
        SELECT custom as device_type, COUNT(*) as total
        FROM processed_data
        GROUP BY custom
    """
    pie_data = run_query(sql)
    
    sql_data = """
        SELECT karama_id, msisdn, cpe, ont, date_, cpe_combine,
               custom, activation_type, year, month, month_num,
               area_name, city, service_plan, customer_type,
               customer_segment, market_type_cd, service_plan_price
        FROM processed_data
        ORDER BY date_
    """
    data = run_query(sql_data)
    
    if not data:
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"PowerBI_Export_{timestamp}.xlsx"
    filepath = os.path.join(EXPORTS_FOLDER, filename)
    chart_image_path = os.path.join(EXPORTS_FOLDER, f"pie_chart_{timestamp}.png")

    # --- 1. Python Library for Pie Chart (Matplotlib) ---
    if pie_data:
        labels = [row['device_type'] if row['device_type'] else 'Unknown' for row in pie_data]
        sizes = [row['total'] for row in pie_data]
        colors = ['#34d4c0', '#f25d6b', '#f0b955', '#636df7']

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', 
               startangle=90, textprops={'color': 'white', 'weight': 'bold'})
        ax.axis('equal')  
        plt.title('Activation Distribution by Device Type', color='white', size=14, weight='bold')
        fig.patch.set_facecolor('#111527') # Match UI dark background
        plt.savefig(chart_image_path, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none', dpi=100)
        plt.close(fig)
import base64
import io

def generate_pie_chart_base64() -> str:
    """Generate a pie chart using Matplotlib and return as base64 string for the UI."""
    sql = """
        SELECT custom as device_type, COUNT(*) as total
        FROM processed_data
        GROUP BY custom
    """
    pie_data = run_query(sql)
    if not pie_data:
        return None

    labels = [row['device_type'] if row['device_type'] else 'Unknown' for row in pie_data]
    sizes = [row['total'] for row in pie_data]
    colors = ['#34d4c0', '#f25d6b', '#f0b955', '#636df7']

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', 
           startangle=90, textprops={'color': 'white', 'weight': 'bold'})
    ax.axis('equal')  
    plt.title('Activation Distribution by Device Type', color='white', size=14, weight='bold')
    fig.patch.set_facecolor('#171c33') # Match UI message bubble background
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none', dpi=100)
    plt.close(fig)
    
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')
    # --- 2. Write to Excel ---
    df = pd.DataFrame(data)
    with pd.ExcelWriter(filepath, engine="xlsxwriter") as writer:
        # Data Sheet
        df.to_excel(writer, sheet_name="Activations Data", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Activations Data"]
        header_format = workbook.add_format({
            "bold": True, "bg_color": "#0f3460", "font_color": "#ffffff", "border": 1,
        })
        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 16)
            
        # Visual/Dashboard Sheet
        if os.path.exists(chart_image_path):
            vis_sheet = workbook.add_worksheet("Dashboard Visuals")
            vis_sheet.set_column('A:Z', 15)
            vis_sheet.write('B2', 'Power BI Pre-Analysis Dashboard', workbook.add_format({'bold': True, 'size': 16}))
            vis_sheet.write('B4', 'Below is the Device Type distribution automatically generated by Matplotlib (Python library).')
            # Insert the Matplotlib generated pie chart
            vis_sheet.insert_image('B6', chart_image_path)

    # Cleanup the temp image
    if os.path.exists(chart_image_path):
        os.remove(chart_image_path)

    return filename
