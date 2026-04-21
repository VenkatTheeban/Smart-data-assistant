import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- Paths ----------
# Allow persistent volume override on Railway/other hosting
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "assistant.db"))
WATCH_FOLDER = os.path.join(BASE_DIR, "watch_folder")
EXPORTS_FOLDER = os.path.join(BASE_DIR, "static", "exports")

# ---------- Gemini API ----------
# Get your FREE API key from: https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ---------- Groq API (fallback if Gemini fails) ----------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---------- App Settings ----------
# Environment-based configuration for hosting platforms (Railway, Render, etc.)
SECRET_KEY = os.environ.get("SECRET_KEY", "smart-data-assistant-secret-key")
DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))