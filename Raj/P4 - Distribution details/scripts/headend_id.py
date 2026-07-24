from __future__ import annotations

import hashlib
import re
import unicodedata

STATE_ALIASES = {
    "allindia": ("All India", "IND"),
    "dth": ("DTH", "DTH"),
    "delhi": ("Delhi", "DEL"),
    "newdelhi": ("Delhi", "DEL"),
    "up": ("Uttar Pradesh", "UP"),
    "u.p": ("Uttar Pradesh", "UP"),
    "uttarpradesh": ("Uttar Pradesh", "UP"),
    "uk": ("Uttarakhand", "UK"),
    "u.k": ("Uttarakhand", "UK"),
    "uttarakhand": ("Uttarakhand", "UK"),
    "uttaranchal": ("Uttarakhand", "UK"),
    "punjab": ("Punjab", "PB"),
    "haryana": ("Haryana", "HR"),
    "hp": ("Himachal Pradesh", "HP"),
    "h.p": ("Himachal Pradesh", "HP"),
    "himachalpradesh": ("Himachal Pradesh", "HP"),
    "jk": ("Jammu & Kashmir", "JK"),
    "j&k": ("Jammu & Kashmir", "JK"),
    "jammuandkashmir": ("Jammu & Kashmir", "JK"),
    "jammukashmir": ("Jammu & Kashmir", "JK"),
    "rajasthan": ("Rajasthan", "RJ"),
    "bihar": ("Bihar", "BR"),
    "jharkhand": ("Jharkhand", "JH"),
    "wb": ("West Bengal", "WB"),
    "w.b": ("West Bengal", "WB"),
    "westbengal": ("West Bengal", "WB"),
    "assamne": ("Assam & North East", "NE"),
    "assamandne": ("Assam & North East", "NE"),
    "assamandnortheast": ("Assam & North East", "NE"),
    "northeast": ("Assam & North East", "NE"),
    "assam": ("Assam", "AS"),
    "mizoram": ("Mizoram", "MZ"),
    "manipur": ("Manipur", "MN"),
    "tripura": ("Tripura", "TR"),
    "meghalaya": ("Meghalaya", "ML"),
    "nagaland": ("Nagaland", "NL"),
    "arunachalpradesh": ("Arunachal Pradesh", "AR"),
    "sikkim": ("Sikkim", "SK"),
    "odisha": ("Odisha", "OD"),
    "orissa": ("Odisha", "OD"),
    "mumbai": ("Mumbai", "MUM"),
    "mahgoa": ("Maharashtra & Goa", "MG"),
    "maharashtragoa": ("Maharashtra & Goa", "MG"),
    "mp": ("Madhya Pradesh", "MP"),
    "m.p": ("Madhya Pradesh", "MP"),
    "madhyapradesh": ("Madhya Pradesh", "MP"),
    "cg": ("Chhattisgarh", "CG"),
    "c.g": ("Chhattisgarh", "CG"),
    "chhattisgarh": ("Chhattisgarh", "CG"),
    "gujarat": ("Gujarat", "GJ"),
    "ap": ("Andhra Pradesh", "AP"),
    "a.p": ("Andhra Pradesh", "AP"),
    "andhrapradesh": ("Andhra Pradesh", "AP"),
    "telangana": ("Telangana", "TG"),
    "karnataka": ("Karnataka", "KA"),
    "maharashtra": ("Maharashtra", "MH"),
}


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def state_lookup_key(value: str | None) -> str:
    normalized = normalize_text(value).replace(" ", "")
    return normalized


def normalize_state(value: str | None) -> str:
    key = state_lookup_key(value)
    if key in STATE_ALIASES:
        return STATE_ALIASES[key][0]

    text = normalize_text(value)
    if not text:
        return "Unknown"
    return " ".join(part.capitalize() for part in text.split())


def state_code(value: str | None) -> str:
    key = state_lookup_key(value)
    if key in STATE_ALIASES:
        return STATE_ALIASES[key][1]

    text = normalize_state(value)
    letters = re.sub(r"[^A-Z]", "", text.upper())
    return (letters[:3] or "UNK")


def extract_known_state(value: str | None) -> str | None:
    normalized = normalize_text(value)
    if not normalized:
        return None

    collapsed = normalized.replace(" ", "")
    for alias_key, (canonical, _) in STATE_ALIASES.items():
        if alias_key and alias_key in collapsed:
            return canonical
    return None


def resolve_state(source_state: str | None, headend_location: str | None, sheet_name: str | None) -> str:
    direct_state = extract_known_state(source_state)
    if direct_state:
        return direct_state

    location_state = extract_known_state(headend_location)
    if location_state:
        return location_state

    if source_state:
        normalized_source = normalize_text(source_state)
        if normalized_source.startswith("district "):
            sheet_state = extract_known_state(sheet_name)
            if sheet_state:
                return sheet_state

    sheet_state = extract_known_state(sheet_name)
    if sheet_state and sheet_state not in {"Assam & North East", "Maharashtra & Goa"}:
        return sheet_state

    text = normalize_text(source_state)
    if not text:
        return normalize_state(sheet_name)
    return " ".join(part.capitalize() for part in text.split())


def generate_headend_id(network_name: str | None, headend_location: str | None, state: str | None) -> str:
    normalized_state = normalize_state(state)
    raw_key = "||".join(
        [
            normalize_text(network_name),
            normalize_text(headend_location),
            normalize_text(normalized_state),
        ]
    )
    digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()[:6]
    return f"{state_code(normalized_state)}-{digest}"
