"""
Gemini and Groq AI Handler
-------------------------
Converts natural language questions into SQL queries,
executes them, and formats the results for the chat UI.
Primary: Gemini, Fallback: Groq.
"""

import json
import re
import time
import urllib.error
import urllib.request

import google.generativeai as genai

from config import GEMINI_API_KEY, GROQ_API_KEY, GROQ_MODEL
from database import get_table_info, get_sample_data, run_query

_client = None

MAX_RETRIES = 3
BASE_WAIT_SECONDS = 10
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Set GEMINI_API_KEY as an environment variable."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        _client = genai.GenerativeModel("gemini-1.5-flash")
    return _client


def _build_system_prompt() -> str:
    schema = get_table_info()

    samples = {}
    for table in ["processed_data"]:
        try:
            samples[table] = get_sample_data(table, 3)
        except Exception:
            samples[table] = []

    return f"""You are a Smart Data Assistant for telecom activation data analysis.
You help users query activation data stored in a SQLite database.

DATABASE SCHEMA:
{json.dumps(schema, indent=2)}

SAMPLE DATA from processed_data:
{json.dumps(samples.get('processed_data', []), indent=2, default=str)}

IMPORTANT TABLE: processed_data (this is the MAIN table to query)
Key columns:
- karama_id: Customer location/premises identifier
- msisdn: Phone number
- cpe: CPE serial number (device)
- ont: ONT serial number (device)
- date_: Date of activation (format: YYYY-MM-DD)
- custom: Device type - values are 'Combo', 'LG', 'DG', 'Other Model'
  - Combo = CPE ends with "CPE" (HIGH PRIORITY device)
  - LG = CPE starts with "48"
  - DG = CPE starts with "21"
- activation_type: values are 'New Installation', 'Reactivation', 'Different Device Used'
- year: e.g. '2025', '2026'
- month: e.g. 'Jan', 'Feb', 'Mar', 'Apr' etc.
- month_num: 1-12
- area_name: Geographic area
- city: City name
- service_plan: Plan name
- customer_type: Residential/Commercial
- service_plan_price: Price of the plan

OTHER TABLES (less commonly used):
- raw_edw: Raw imported data before processing
- service_dump: Historical device records

BUSINESS RULES:
- "activation" refers to records in processed_data
- "COMBO" = custom = 'Combo' (case sensitive in DB)
- "reactivation" = activation_type = 'Reactivation'
- "new activation" = activation_type = 'New Installation'
- "different device" = activation_type = 'Different Device Used'
- Month names are stored as 3-letter abbreviations: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec

INSTRUCTIONS:
1. When the user asks a question, generate a SQLite-compatible SQL query.
2. Return your response in this exact JSON format:
{{
  "sql": "SELECT ... FROM processed_data ...",
  "explanation": "Brief explanation of what the query does",
  "response_type": "table" or "summary" or "chart",
  "chart_config": {{"type": "bar/line/pie", "title": "...", "x_label": "...", "y_label": "..."}}
}}

3. chart_config is only needed if response_type is "chart".
4. For monthly reports, include total activations, breakdowns by custom type, activation type, and percentage calculations.
5. Always use the processed_data table unless the user specifically asks about raw data or service dump.
6. For "report" requests, provide comprehensive data with multiple metrics.
7. If the user asks to "download" or "export", set response_type to "download".
8. If the user asks for trends or comparisons, use response_type "chart".
9. ONLY generate SELECT statements. Never generate INSERT, UPDATE, DELETE, DROP, or any modifying queries.
10. For percentage calculations, use ROUND(CAST(x AS FLOAT) / y * 100, 1).
11. When the user says "Power BI report", generate a comprehensive query with all key fields for export.

RESPOND ONLY WITH THE JSON. No markdown, no code fences, no extra text."""


def _call_gemini_with_retry(client, system_prompt: str, user_question: str) -> str:
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.generate_content(
                f"{system_prompt}\n\nUser question: {user_question}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                ),
            )
            return (response.text or "").strip()
        except Exception as e:
            error_str = str(e)
            last_error = e
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                wait_time = BASE_WAIT_SECONDS * (2 ** attempt)
                print(f"[GEMINI] Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait_time)
                continue
            raise

    raise last_error


def _call_groq(system_prompt: str, user_question: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.1,
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User question: {user_question}"},
        ],
    }

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Groq network error: {e}") from e

    data = json.loads(body)
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("Groq returned no choices.")

    content = choices[0].get("message", {}).get("content", "")
    return content.strip()


def _extract_json(raw: str) -> dict:
    txt = (raw or "").strip()

    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)

    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", txt, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _execute_ai_output(raw: str, provider: str, fallback_note: str = "") -> dict:
    parsed = _extract_json(raw)

    sql = parsed.get("sql", "")
    explanation = parsed.get("explanation", "")
    response_type = parsed.get("response_type", "table")
    chart_config = parsed.get("chart_config", None)

    if not sql.strip().upper().startswith("SELECT"):
        return {
            "success": False,
            "error": "I can only run SELECT queries for safety.",
            "explanation": explanation,
        }

    results = run_query(sql)

    final_explanation = explanation
    if fallback_note:
        final_explanation = f"{fallback_note}\n\n{explanation}" if explanation else fallback_note

    return {
        "success": True,
        "sql": sql,
        "explanation": final_explanation,
        "response_type": response_type,
        "chart_config": chart_config,
        "data": results,
        "row_count": len(results),
        "provider": provider,
    }


def ask_gemini(user_question: str) -> dict:
    """
    Primary path: Gemini
    Fallback path: Groq (if Gemini fails or returns invalid JSON)
    """
    system_prompt = _build_system_prompt()

    gemini_error = None
    try:
        client = _get_client()
        raw = _call_gemini_with_retry(client, system_prompt, user_question)
        return _execute_ai_output(raw, provider="gemini")
    except Exception as e:
        gemini_error = str(e)
        print(f"[AI] Gemini failed, trying Groq fallback. Reason: {gemini_error}")

    if GROQ_API_KEY:
        try:
            raw = _call_groq(system_prompt, user_question)
            return _execute_ai_output(
                raw,
                provider="groq",
                fallback_note="Gemini is currently unavailable. Answer generated via Groq fallback.",
            )
        except Exception as groq_error:
            return {
                "success": False,
                "error": f"Gemini failed: {gemini_error}. Groq fallback failed: {groq_error}",
            }

    return {
        "success": False,
        "error": f"Gemini failed: {gemini_error}. Groq fallback not configured. Set GROQ_API_KEY.",
    }


def format_response_as_text(result: dict) -> str:
    if not result.get("success"):
        return f"Error: {result.get('error', 'Something went wrong.')}"

    data = result.get("data", [])
    explanation = result.get("explanation", "")
    row_count = result.get("row_count", 0)

    if row_count == 0:
        return f"{explanation}\n\nNo data found for your query."

    lines = [f"{explanation}", f"Found {row_count} result(s):", ""]

    if row_count <= 30:
        if data:
            headers = list(data[0].keys())
            lines.append(" | ".join(headers))
            lines.append("-" * len(" | ".join(headers)))
            for row in data:
                lines.append(" | ".join(str(row.get(h, "")) for h in headers))
    else:
        headers = list(data[0].keys())
        lines.append(" | ".join(headers))
        lines.append("-" * len(" | ".join(headers)))
        for row in data[:20]:
            lines.append(" | ".join(str(row.get(h, "")) for h in headers))
        lines.append(f"\n... and {row_count - 20} more rows.")
        lines.append("Ask me to download/export this data for the full dataset.")

    return "\n".join(lines)
