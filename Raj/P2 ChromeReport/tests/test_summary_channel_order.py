from pathlib import Path
import importlib.util


spec = importlib.util.spec_from_file_location("app", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_india_tv_is_prioritized_in_summary_channel_order():
    channels = ["NEWS 18 INDIA", "REPUBLIC BHARAT", "AAJ TAK", "INDIA TV"]
    assert app.sort_summary_channels(channels) == ["INDIA TV", "AAJ TAK", "NEWS 18 INDIA", "REPUBLIC BHARAT"]
