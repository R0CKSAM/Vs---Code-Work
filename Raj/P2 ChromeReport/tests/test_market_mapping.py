from pathlib import Path
import importlib.util


spec = importlib.util.spec_from_file_location("market_mapping", Path(__file__).resolve().parents[1] / "market_mapping.py")
market_mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market_mapping)


def test_supports_nested_field_mappings():
    market_mapping.load_all_mappings.cache_clear()
    original_file = market_mapping.MARKET_MAPPING_FILE
    fixture_file = Path(__file__).resolve().parent / "_tmp_market_mapping.json"
    fixture_file.write_text(
        """
{
  "market": {"delhi ncr": "DELHI"},
  "city": {"gurgaon": "GURUGRAM"},
  "head_end": {"airtel digital": "AIRTEL DTH"},
  "channel_name": {"news18 india": "NEWS 18 INDIA"}
}
""".strip(),
        encoding="utf-8",
    )
    market_mapping.MARKET_MAPPING_FILE = fixture_file
    try:
        assert market_mapping.normalize_market_name("Delhi NCR") == "DELHI"
        assert market_mapping.normalize_city_name("gurgaon") == "GURUGRAM"
        assert market_mapping.normalize_headend_name("Airtel Digital") == "AIRTEL DTH"
        assert market_mapping.normalize_channel_name("News18 India") == "NEWS 18 INDIA"
        assert market_mapping.normalize_channel_name("India TV") == "India TV"
    finally:
        market_mapping.MARKET_MAPPING_FILE = original_file
        market_mapping.load_all_mappings.cache_clear()
        if fixture_file.exists():
            fixture_file.unlink()
