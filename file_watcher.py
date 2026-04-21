"""
File Watcher
────────────
Monitors the watch_folder/ directory for new .xlsx files.
Auto-imports and processes them when detected.
"""

import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import WATCH_FOLDER
from database import import_raw_edw, import_service_dump
from business_logic import process_all

# Shared state for the UI to poll
watcher_events = []


class ExcelFileHandler(FileSystemEventHandler):
    """Handles new Excel files dropped into watch_folder."""

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(".xlsx"):
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)

        print(f"[WATCHER] New file detected: {filename}")
        watcher_events.append({
            "type": "file_detected",
            "filename": filename,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        # Wait a moment for the file to finish writing
        time.sleep(3)

        # Try to figure out what kind of file this is
        try:
            if "dump" in filename.lower() or "service" in filename.lower():
                result = import_service_dump(filepath)
            else:
                result = import_raw_edw(filepath)

            print(f"[WATCHER] Import result: {result}")
            watcher_events.append({
                "type": "import_complete",
                "filename": filename,
                "result": result,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

            # Re-process all data with business logic
            if result.get("status") == "success":
                print("[WATCHER] Re-processing data with business logic...")
                proc_result = process_all()
                print(f"[WATCHER] Processing result: {proc_result}")
                watcher_events.append({
                    "type": "processing_complete",
                    "result": proc_result,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

        except Exception as e:
            print(f"[WATCHER] Error processing {filename}: {e}")
            watcher_events.append({
                "type": "error",
                "filename": filename,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })


# ──────────────────────────────────────────────
# Start / stop the watcher
# ──────────────────────────────────────────────

_observer = None


def start_watcher():
    """Start the file watcher in a background thread."""
    global _observer
    if _observer is not None:
        return  # Already running

    os.makedirs(WATCH_FOLDER, exist_ok=True)
    handler = ExcelFileHandler()
    _observer = Observer()
    _observer.schedule(handler, WATCH_FOLDER, recursive=False)
    _observer.daemon = True
    _observer.start()
    print(f"[WATCHER] Watching folder: {WATCH_FOLDER}")


def stop_watcher():
    """Stop the file watcher."""
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
        print("[WATCHER] Stopped.")


def get_recent_events(limit: int = 10) -> list:
    """Return recent watcher events for the UI."""
    return watcher_events[-limit:]
