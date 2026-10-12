"""
Media Reporting System - Server Launcher Helper
Launches the FastAPI backend and static web dashboard on http://127.0.0.1:8000.
"""
import sys
import os
import logging
from pathlib import Path

# Ensure both the backend/ directory and the project root are on sys.path.
# This is required so that:
#   - app.* imports resolve from backend/
#   - database.* imports resolve from the project root
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for _p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_server")


def initialize_database() -> None:
    """
    Idempotent Phase 4 schema initialization run before the server starts.
    CREATE TABLE IF NOT EXISTS — no data is ever deleted or reset.
    """
    try:
        from database.schema import init_db
        init_db()
        logger.info("Database schema initialized (idempotent).")
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        raise


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("[!] 'uvicorn' package is not installed in this Python environment.")
        print("[!] Run: python -m pip install -r backend/requirements.txt")
        sys.exit(1)

    # Initialize DB schema before uvicorn starts
    initialize_database()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    lan_ip = "192.168.50.134"

    print("=" * 70)
    print("  MEDIA REPORTING - FASTAPI SERVER (LOCAL + LAN)")
    print(f"  Local Access : http://127.0.0.1:{port}/")
    print(f"  LAN Access   : http://{lan_ip}:{port}/")
    print(f"  API Docs     : http://127.0.0.1:{port}/docs")
    print("=" * 70)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        app_dir=str(BACKEND_DIR),
        reload=False,
    )

