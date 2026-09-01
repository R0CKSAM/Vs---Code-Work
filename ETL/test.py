import os
import sys
import json
from pathlib import Path

import requests


TOOLS_DIR = Path(__file__).resolve().parent / "src" / "tools"
sys.path.insert(0, str(TOOLS_DIR))
import decode_distinct_ua_lookup as decoder  # noqa: E402


decoder.load_env_file()
key = os.environ["WHATMYUA_KEY"]
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

response = requests.get(
    decoder.DEFAULT_API_URL,
    params={"ua": ua, "key": key},
    timeout=20,
)
if not response.ok:
    try:
        error_payload = response.json()
        error_message = error_payload.get("error") or error_payload.get("message") or error_payload
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError):
        error_message = response.text[:300]
    raise SystemExit(f"API request failed: HTTP {response.status_code}: {error_message}")
data = response.json()

print(data.get("Browser", {}).get("name", "Unknown"))
print(data.get("OS", {}).get("name", "Unknown"))
print(data.get("Device", {}).get("brand", "Unknown"))
