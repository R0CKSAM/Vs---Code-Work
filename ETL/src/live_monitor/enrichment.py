from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus


ETL_ROOT = Path(__file__).resolve().parents[2]
UA_LOOKUP_PATH = ETL_ROOT / "output" / "device_decode" / "ua_decode_lookup_both_all.parquet"
ASN_LOOKUP_PATH = ETL_ROOT / "data" / "asn" / "ip2location_asn_cache.json"

_LOCK = threading.RLock()
_UA_STATE: tuple[int, dict[str, dict[str, str]]] = (-1, {})
_ASN_STATE: tuple[int, dict[str, dict[str, str]]] = (-1, {})


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return -1


def normalize_ua(value: Any) -> str:
    text = str(value or "").strip()
    for _ in range(5):
        decoded = unquote_plus(text).strip()
        if decoded == text:
            break
        text = decoded
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in {"", "nan", "none", "null", "unknown", "unknown / na"} else text


def _joined(record: dict[str, str], names: tuple[str, ...]) -> str:
    return " ".join(part for name in names if (part := _clean(record.get(name)))).strip()


def _ua_lookup() -> dict[str, dict[str, str]]:
    global _UA_STATE
    stamp = _mtime(UA_LOOKUP_PATH)
    if stamp == _UA_STATE[0]:
        return _UA_STATE[1]
    with _LOCK:
        if stamp == _UA_STATE[0]:
            return _UA_STATE[1]
        lookup: dict[str, dict[str, str]] = {}
        if stamp >= 0:
            try:
                import pyarrow.parquet as parquet

                columns = (
                    "ua_hash", "decode_status", "confidence", "device_type",
                    "form_factor", "brand", "model", "os_name", "os_version",
                    "browser_name", "browser_version", "app_player", "is_bot",
                    "api_device_type", "api_brand", "api_model", "api_os_name",
                    "api_os_version", "api_browser_name", "api_browser_version",
                )
                schema_names = set(parquet.read_schema(UA_LOOKUP_PATH).names)
                selected = [name for name in columns if name in schema_names]
                for row in parquet.read_table(UA_LOOKUP_PATH, columns=selected).to_pylist():
                    key = _clean(row.get("ua_hash"))
                    if key:
                        lookup[key] = {name: _clean(value) for name, value in row.items()}
            except (OSError, ValueError, ImportError, json.JSONDecodeError):
                lookup = {}
        _UA_STATE = (stamp, lookup)
        return lookup


def _asn_lookup() -> dict[str, dict[str, str]]:
    global _ASN_STATE
    stamp = _mtime(ASN_LOOKUP_PATH)
    if stamp == _ASN_STATE[0]:
        return _ASN_STATE[1]
    with _LOCK:
        if stamp == _ASN_STATE[0]:
            return _ASN_STATE[1]
        lookup: dict[str, dict[str, str]] = {}
        if stamp >= 0:
            try:
                payload = json.loads(ASN_LOOKUP_PATH.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    lookup = {
                        str(key): value for key, value in payload.items()
                        if isinstance(value, dict)
                    }
            except (OSError, ValueError, json.JSONDecodeError):
                lookup = {}
        _ASN_STATE = (stamp, lookup)
        return lookup


def decoded_ua_dimensions(value: Any) -> dict[str, str]:
    normalized = normalize_ua(value)
    if not normalized:
        return {"ua_decode_status": "UA missing"}
    key = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()
    record = _ua_lookup().get(key)
    if not record:
        return {"ua_decode_status": "Not in lookup"}

    status = _clean(record.get("decode_status")) or "Decoded"
    device = _clean(record.get("device_type")) or _clean(record.get("api_device_type"))
    brand = _clean(record.get("brand")) or _clean(record.get("api_brand"))
    model = _clean(record.get("model")) or _clean(record.get("api_model"))
    os_label = _joined(record, ("os_name", "os_version")) or _joined(
        record, ("api_os_name", "api_os_version")
    )
    browser = _joined(record, ("browser_name", "browser_version")) or _joined(
        record, ("api_browser_name", "api_browser_version")
    )
    values = {
        "ua_decode_status": status,
        "device_type_decoded": device,
        "form_factor_decoded": _clean(record.get("form_factor")),
        "brand_decoded": brand,
        "model_decoded": model,
        "os_decoded": os_label,
        "browser_decoded": browser,
        "player_decoded": _clean(record.get("app_player")),
        "client_class": "Bot" if _clean(record.get("is_bot")).casefold() in {"1", "true", "yes"} else "Human / device",
    }
    return {name: value or "Not exposed in UA" for name, value in values.items()}


def decoded_asn_dimensions(value: Any) -> dict[str, str]:
    asn = re.sub(r"(?i)^as", "", str(value or "").strip())
    if not asn or asn == "-":
        return {"asn_decode_status": "ASN missing"}
    record = _asn_lookup().get(asn)
    if not record:
        return {"asn_decode_status": "Not in lookup"}
    status = _clean(record.get("status")) or _clean(record.get("lookup_status")) or "Decoded"
    return {
        "asn_decode_status": status,
        "network_provider": _clean(record.get("as_name")) or "Provider not exposed",
        "network_type": _clean(record.get("asn_type")) or "Type not exposed",
        "network_country": _clean(record.get("as_country")) or "Country not exposed",
    }
