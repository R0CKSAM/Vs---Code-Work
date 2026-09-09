from __future__ import annotations

import subprocess
import sys


def main() -> None:
    worker = subprocess.Popen([sys.executable, "-m", "app.worker"])
    api = subprocess.Popen([sys.executable, "run_api.py"])
    try:
        api.wait()
    except KeyboardInterrupt:
        pass
    finally:
        worker.terminate()
        api.terminate()
        worker.wait(timeout=10)
        api.wait(timeout=10)


if __name__ == "__main__":
    main()

