from __future__ import annotations

import sys
import json
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ETL" / "src" / "tools"))

from api_sanity_check_ua_statuses import decoder, select_candidates  # noqa: E402


def test_candidates_follow_requested_status_order_and_retry_errors():
    lookup = pd.DataFrame(
        [
            {"ua_hash": "local", "ua_norm": "Local/1", "decode_status": "decoded_local", "confidence": "high", "is_malformed": False},
            {"ua_hash": "unknown-error", "ua_norm": "Unknown/1", "decode_status": "unknown", "confidence": "low", "is_malformed": False},
            {"ua_hash": "unknown-ok", "ua_norm": "Unknown/2", "decode_status": "unknown", "confidence": "low", "is_malformed": False},
        ]
    )
    cache = pd.DataFrame(
        [
            {"ua_hash": "unknown-error", "api_status": "api_error"},
            {"ua_hash": "unknown-ok", "api_status": "decoded_api"},
        ]
    )
    args = Namespace(
        statuses="unknown,decoded_local",
        include_malformed=False,
        force=False,
        api_limit=-1,
    )

    result = select_candidates(lookup, cache, args)

    assert result["ua_hash"].tolist() == ["unknown-error", "local"]


def test_standard_http_429_is_recognized_as_rate_limit():
    assert decoder.is_rate_limit_error("HTTP Error 429: Too Many Requests")
    assert decoder.is_rate_limit_error("API rate limit exceeded")
    assert not decoder.is_rate_limit_error("HTTP Error 500: Internal Server Error")


def test_authentication_errors_are_fatal():
    assert decoder.is_auth_error("HTTP Error 401: Unauthorized")
    assert decoder.is_auth_error("HTTP Error 403: Forbidden")
    assert not decoder.is_auth_error("HTTP Error 429: Too Many Requests")


def test_authenticated_api_request_uses_documented_key_parameter(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"Browser": {}, "OS": {}, "Device": {}}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(decoder.urllib.request, "urlopen", fake_urlopen)
    args = Namespace(api_key="test-secret", api_url=decoder.DEFAULT_API_URL, api_timeout=20)

    decoder.api_decode("Example/1.0", args)

    assert captured["request"].get_header("Authorization") is None
    assert "key=test-secret" in captured["request"].full_url
    assert captured["timeout"] == 20
