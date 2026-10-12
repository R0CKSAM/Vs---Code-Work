"""
comparator.py – State comparison, normalization, and fingerprinting for FanCode entities.

Compares normalized previous and current entity states, handling whitespace, URLs,
datetimes, and ensuring omitted fields (None) do not falsely trigger deletion changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.scraper.discovery.url_normalizer import normalize as normalize_url

logger = logging.getLogger(__name__)


class StateComparator:
    """Provides pure, normalized field comparison and fingerprinting."""

    @staticmethod
    def normalize_for_comparison(val: Any) -> Optional[str]:
        """
        Convert values to consistent string representation for accurate comparison.
        Collapses whitespace, normalizes URLs, and canonicalizes ISO timestamps.
        """
        if val is None:
            return None

        # Datetime / date
        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            else:
                val = val.astimezone(timezone.utc)
            return val.strftime("%Y-%m-%dT%H:%M:%SZ")

        if isinstance(val, date):
            return val.strftime("%Y-%m-%d")

        # Boolean
        if isinstance(val, bool):
            return "true" if val else "false"

        # Number
        if isinstance(val, (int, float)):
            return str(val)

        # String
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            # Check if URL
            if s.startswith("http://") or s.startswith("https://"):
                norm = normalize_url(s)
                return norm or s
            # Collapse multiple spaces
            return re.sub(r"\s+", " ", s)

        return str(val).strip()

    @classmethod
    def are_values_equal(cls, old_val: Any, new_val: Any) -> bool:
        """
        Check equality of two values.
        Critical Rule (Section 15): If new_val is None, it means the scraper did not
        observe/expose the field on this run; it must NOT be treated as a change.
        """
        if new_val is None:
            return True

        norm_old = cls.normalize_for_comparison(old_val)
        norm_new = cls.normalize_for_comparison(new_val)

        return norm_old == norm_new

    @classmethod
    def compare_fields(
        cls,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        tracked_fields: List[str],
    ) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """
        Compares tracked fields between two snapshots.
        Returns a dict of {field_name: (old_normalized, new_normalized)} for fields that changed.
        """
        changed: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

        for field in tracked_fields:
            if field not in new_data:
                continue

            old_v = old_data.get(field)
            new_v = new_data.get(field)

            # If new_v is None, treat as unobserved (do not change)
            if new_v is None:
                continue

            # For status field: incoming UNKNOWN or unverified status represents an unobserved
            # status from the scraper and must NOT be treated as a status change.
            if field == "status":
                norm_new_s = (cls.normalize_for_comparison(new_v) or "").upper()
                if norm_new_s in ("UNKNOWN", "UNCONFIRMED", "UNVERIFIED", "", "NONE", "NULL"):
                    continue

            # If old_v is None, the DB never had data for this field.
            # Incoming data filling it in is initial enrichment, NOT a
            # meaningful change worth generating a notification event for.
            if old_v is None:
                continue

            if not cls.are_values_equal(old_v, new_v):
                changed[field] = (
                    cls.normalize_for_comparison(old_v),
                    cls.normalize_for_comparison(new_v),
                )

        return changed

    @classmethod
    def compute_fingerprint(cls, entity_data: Dict[str, Any], meaningful_fields: List[str]) -> str:
        """
        Computes a stable deterministic SHA256 hash over normalized meaningful fields,
        excluding noise like score, live timers, and volatile metadata.
        """
        normalized_dict: Dict[str, Optional[str]] = {}
        for f in sorted(meaningful_fields):
            v = entity_data.get(f)
            normalized_dict[f] = cls.normalize_for_comparison(v)

        serialized = json.dumps(normalized_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def compute_entity_fingerprint(cls, entity_data: Dict[str, Any], meaningful_fields: Optional[List[str]] = None) -> str:
        """Convenience method / alias to compute deterministic hash."""
        fields = meaningful_fields if meaningful_fields is not None else list(entity_data.keys())
        return cls.compute_fingerprint(entity_data, fields)
