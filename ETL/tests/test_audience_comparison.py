from datetime import date
from pathlib import Path
import sys
import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
from compare_audience_periods import compare, normalize_ip, validate_periods


def test_period_uniques_and_scope(tmp_path):
    index = tmp_path / "index.parquet"
    con = duckdb.connect()
    con.execute("""CREATE TABLE data(log_date DATE, source VARCHAR, cliIP VARCHAR,
                   channel_name VARCHAR, statusCode VARCHAR, raw_ts_rows INT)""")
    con.executemany("INSERT INTO data VALUES (?,?,?,?,?,?)", [
        ("2026-01-01", "stream", "1.1.1.1", "A", "200", 10),
        ("2026-01-02", "stream", "1.1.1.1", "A", "200", 10),
        ("2026-01-02", "stream", "2.2.2.2", "B", "200", 1),
        ("2026-01-03", "stream", "::ffff:1.1.1.1", "B", "200", 1),
        ("2026-01-03", "stream", "3.3.3.3", "A", "200", 1),
        ("2026-01-03", "stream", "4.4.4.4", "A", "500", 1),
        ("2026-01-03", "fast", "5.5.5.5", "A", "200", 1),
    ])
    con.execute("COPY data TO ? (FORMAT PARQUET)", [str(index)])
    con.close()
    audit = dict(daily=[dict(date=f"2026-01-0{d}", sources=[dict(source="stream", status="PASS", selected=dict(full_day=True))]) for d in (1,2,3)])
    args = (index, audit, "stream", date(2026,1,1), date(2026,1,2), date(2026,1,3), date(2026,1,3))
    result = compare(*args)
    total = result["rows"][0]
    assert total["baseline_ips"] == total["target_ips"] == 2
    assert total["returning_ips"] == total["new_to_baseline_ips"] == total["not_seen_again_ips"] == 1
    assert total["returning_share_pct"] == total["baseline_retention_pct"] == 50
    assert compare(*args, all_http=True)["rows"][0]["target_ips"] == 3
    assert compare(*args, channels=["A"])["rows"][0]["returning_ips"] == 0
    assert compare(*args, channels=["missing"])["rows"][0]["returning_share_pct"] is None
    audit["daily"][0]["sources"][0]["status"] = "PARTIAL"
    with pytest.raises(ValueError, match="full-day"):
        compare(*args)


def test_identity_and_overlap():
    assert normalize_ip("2001:0db8::1") == "2001:db8::1"
    assert normalize_ip("unknown") is None
    with pytest.raises(ValueError, match="overlap"):
        validate_periods(date(2026,1,1), date(2026,1,3), date(2026,1,3), date(2026,1,4))
