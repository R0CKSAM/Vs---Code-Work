from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
MARKET_MAPPING_FILE = BASE_DIR / "market_mapping.json"
SUPPORTED_FIELDS = ("market", "city", "head_end", "channel_name")


def _normalize_key(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_mapping(values: dict[Any, Any]) -> dict[str, str]:
    return {
        _normalize_key(key): str(value).strip()
        for key, value in values.items()
        if str(value).strip()
    }


@lru_cache(maxsize=1)
def load_all_mappings() -> dict[str, dict[str, str]]:
    empty = {field: {} for field in SUPPORTED_FIELDS}
    if not MARKET_MAPPING_FILE.exists():
        return empty

    data = json.loads(MARKET_MAPPING_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return empty

    # Backward compatibility: a flat object is treated as the legacy market-only mapping.
    if data and all(isinstance(value, str) for value in data.values()):
        empty["market"] = _clean_mapping(data)
        return empty

    mappings = dict(empty)
    for field in SUPPORTED_FIELDS:
        raw_field_mapping = data.get(field, {})
        if isinstance(raw_field_mapping, dict):
            mappings[field] = _clean_mapping(raw_field_mapping)
    return mappings


def load_market_mapping() -> dict[str, str]:
    return load_all_mappings()["market"]


def load_city_mapping() -> dict[str, str]:
    return load_all_mappings()["city"]


def load_headend_mapping() -> dict[str, str]:
    return load_all_mappings()["head_end"]


def load_channel_name_mapping() -> dict[str, str]:
    return load_all_mappings()["channel_name"]


def normalize_mapped_value(field: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    mapping = load_all_mappings().get(field, {})
    return mapping.get(_normalize_key(text), text)


def normalize_market_name(value: object) -> str:
    return normalize_mapped_value("market", value)


def normalize_city_name(value: object) -> str:
    return normalize_mapped_value("city", value)


def normalize_headend_name(value: object) -> str:
    return normalize_mapped_value("head_end", value)


def normalize_channel_name(value: object) -> str:
    return normalize_mapped_value("channel_name", value)
