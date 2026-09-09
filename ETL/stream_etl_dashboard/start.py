"""Start the corrected ETL worker and dashboard from any working directory."""
from __future__ import annotations

import subprocess
import sys
import socket
from pathlib import Path

from app.config import settings


def main() -> None:
    root = Path(__file__).resolve().parent
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", settings.api_port)) == 0:
            print(f"Dashboard is already running at http://localhost:{settings.api_port}")
            print("Stop the existing instance before starting another one.")
            return
    worker = subprocess.Popen([sys.executable, "-m", "app.worker_live"], cwd=root)
    api = subprocess.Popen([sys.executable, "run_api.py"], cwd=root)
    print("Dashboard: http://localhost:8788")
    try:
        api.wait()
    except KeyboardInterrupt:
        pass
    finally:
        worker.terminate()
        api.terminate()
        for process in (worker, api):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
