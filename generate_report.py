"""
Generate a report matching Query.xlsx format from the database.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import run_query
import pandas as pd

# === 1. Monthly Summary (matching Query.xlsx Sheet3) ===
print("=== MONTHLY SUMMARY (matching Query.xlsx Sheet3) ===\n")

summary = run_query("""
    SELECT year, month, month_num,
           COUNT(*) as total_activation,
           SUM(CASE WHEN custom = 'Combo' AND activation_type = 'Reactivation' THEN 1 ELSE 0 END) as reactivation_combo,
           ROUND(CAST(SUM(CASE WHEN custom = 'Combo' AND activation_type = 'Reactivation' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*), 4) as reactivation_combo_pct
    FROM processed_data
    WHERE year IS NOT NULL
    GROUP BY year, month, month_num
    ORDER BY year, month_num
""")

print(f"{'Year':<8} {'Month':<8} {'Total':<10} {'React Combo':<14} {'React Combo %':<15}")
print("-" * 55)
for row in summary:
    pct_str = f"{row['reactivation_combo_pct']*100:.2f}%" if row['reactivation_combo_pct'] else "0.00%"
    print(f"{row['year']:<8} {row['month']:<8} {row['total_activation']:<10} {row['reactivation_combo']:<14} {pct_str:<15}")

# Grand Total
totals = run_query("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN custom = 'Combo' AND activation_type = 'Reactivation' THEN 1 ELSE 0 END) as react_combo
    FROM processed_data
""")
t = totals[0]
pct = t['react_combo'] / t['total'] * 100 if t['total'] else 0
print("-" * 55)
print(f"{'Total':<8} {'':<8} {t['total']:<10} {t['react_combo']:<14} {pct:.2f}%")

# === 2. Original Query.xlsx comparison values ===
print("\n\n=== COMPARISON WITH ORIGINAL Query.xlsx Sheet3 ===\n")
print("Original Query.xlsx values:")
originals = [
    ("2025", "Aug", 4549, 276, 6.07),
    ("2025", "Sep", 4610, 401, 8.70),
    ("2025", "Oct", 4119, 416, 10.10),
    ("2025", "Nov", 3911, 410, 10.48),
    ("2025", "Dec", 3752, 556, 14.82),
    ("2026", "Jan", 4007, 623, 15.55),
    ("2026", "Feb", 3444, 626, 18.18),
    ("2026", "Mar", 3327, 707, 21.25),
    ("2026", "Apr", 1083, 222, 20.50),
]
print(f"{'Year':<8} {'Month':<8} {'Total':<10} {'React Combo':<14} {'React Combo %':<15}")
print("-" * 55)
for yr, mo, tot, rc, pct in originals:
    print(f"{yr:<8} {mo:<8} {tot:<10} {rc:<14} {pct:.2f}%")
print("-" * 55)
print(f"{'Total':<8} {'':<8} {32802:<10} {4237:<14} {12.92:.2f}%")

# === 3. Custom type and Activation type distribution ===
print("\n\n=== CUSTOM TYPE DISTRIBUTION ===\n")
custom = run_query("SELECT custom, COUNT(*) as cnt FROM processed_data GROUP BY custom ORDER BY cnt DESC")
for row in custom:
    print(f"  {row['custom']:<15} {row['cnt']}")

print("\n=== ACTIVATION TYPE DISTRIBUTION ===\n")
act = run_query("SELECT activation_type, COUNT(*) as cnt FROM processed_data GROUP BY activation_type ORDER BY cnt DESC")
for row in act:
    print(f"  {row['activation_type']:<25} {row['cnt']}")

# === 4. Export to Excel matching Query.xlsx format ===
print("\n\n=== GENERATING EXCEL REPORT ===\n")

# Data sheet
data_rows = run_query("""
    SELECT karama_id as KID, msisdn as MSISDN, cpe as CPE, ont as ONT, 
           date_ as Date, cpe_combine as 'CPE Combine', custom as Custom, 
           activation_type as 'Activation Count'
    FROM processed_data
    ORDER BY date_
""")
df_data = pd.DataFrame(data_rows)

# Summary sheet
df_summary = pd.DataFrame(summary)
df_summary.columns = ['Date (Year)', 'Date (Month)', 'month_num', 'Total Activation', 'Reactivation Combo', 'Reactivation Combo %']
df_summary = df_summary.drop(columns=['month_num'])

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "exports", "Query_Report_from_DB.xlsx")
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
    df_data.to_excel(writer, sheet_name="Data", index=False)
    df_summary.to_excel(writer, sheet_name="Summary", index=False)
    
    workbook = writer.book
    
    # Format Data sheet
    ws_data = writer.sheets["Data"]
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1a1a2e', 'font_color': '#e94560', 'border': 1})
    for i, col in enumerate(df_data.columns):
        ws_data.write(0, i, col, header_fmt)
        ws_data.set_column(i, i, 18)
    
    # Format Summary sheet
    ws_sum = writer.sheets["Summary"]
    for i, col in enumerate(df_summary.columns):
        ws_sum.write(0, i, col, header_fmt)
        ws_sum.set_column(i, i, 20)
    
    # Format percentage column
    pct_fmt = workbook.add_format({'num_format': '0.00%'})
    for row_idx in range(len(df_summary)):
        ws_sum.write(row_idx + 1, 4, df_summary.iloc[row_idx]['Reactivation Combo %'], pct_fmt)

print(f"Report saved to: {output_path}")
print(f"Data sheet rows: {len(df_data)}")
print(f"Summary sheet rows: {len(df_summary)}")
print("\nDone!")
