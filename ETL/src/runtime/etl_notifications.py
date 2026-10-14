"""Persist ETL failure alerts and show a nonblocking Windows desktop popup."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from uuid import uuid4

ETL = Path(__file__).resolve().parents[2]


def notify_failure(step, error, log_path=None, state_path=None, *, popup=True, alert_dir=None):
    try:
        directory = Path(alert_dir) if alert_dir else ETL / 'output/alerts'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"failure_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.json"
        payload = dict(step=str(step), error=str(error)[:1800],
                       log_path=str(log_path or ''), state_path=str(state_path or ''),
                       created_at=datetime.now().isoformat(), acknowledged=False)
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        if popup and sys.platform == 'win32' and os.environ.get('VG_ETL_NOTIFY_FAILURES', '1') != '0':
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            subprocess.Popen(['powershell.exe', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass',
                '-File', str(ETL / 'show_etl_failure.ps1'), '-AlertFile', str(path)],
                startupinfo=startup, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        return path
    except Exception as exc:
        print(f'Could not deliver ETL failure notification: {exc}', file=sys.stderr, flush=True)
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', required=True)
    parser.add_argument('--error', required=True)
    parser.add_argument('--log-path')
    parser.add_argument('--state-path')
    args = parser.parse_args()
    notify_failure(args.step, args.error, args.log_path, args.state_path)
