"""Keep the lake/report mapping aligned with the approved live feed IDs."""

import json
import sys
from pathlib import Path

import duckdb
import pytest

ETL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL))

from src.profile import vglive_core as core
from src.tools import build_concurrency

SCHEDULE = json.loads(
    (ETL / "config/live_monitor/davis_cup_2026_schedule.json").read_text()
)
ASSETS = sorted({event["asset_id"] for event in SCHEDULE["events"]})


@pytest.mark.parametrize("asset", ASSETS)
def test_python_mapping_and_unknown_prefix(asset):
    expected = f"Davis Cup ({asset[:5]})"
    assert core.resolve_channel("daviscup-veto.akamaized.net", asset.upper()) == expected
    assert core.resolve_channel("daviscup-veto.akamaized.net", asset[:5]) == "Other"
    assert core.resolve_channel("daviscup-veto.akamaized.net", asset + "0") == "Other"


@pytest.mark.parametrize("register", [core._register_mapping_tables, build_concurrency.register_maps])
def test_report_sql_preserves_rows_and_totals(register):
    with duckdb.connect() as con:
        register(con)
        con.execute("CREATE TABLE requests(reqPath VARCHAR, bytes BIGINT)")
        con.executemany(
            "INSERT INTO requests VALUES (?, ?)",
            [(f"/{asset}/playlist_4_100.ts", 100) for asset in ASSETS]
            + [("/not-a-known-feed/playlist_4_100.ts", 50)],
        )
        rows = con.execute(f"""
            SELECT COALESCE(p.path_channel_name, 'Other'), count(*), sum(bytes)
            FROM requests r
            LEFT JOIN path_map p ON ({core.channel_candidate_sql('r.reqPath')}) = p.candidate_id
            GROUP BY 1
        """).fetchall()
    assert len(rows) == 7
    assert sum(row[1] for row in rows) == 7
    assert sum(row[2] for row in rows) == 650
    assert {row[0] for row in rows} == {f"Davis Cup ({a[:5]})" for a in ASSETS} | {"Other"}


def test_existing_channels_unchanged():
    assert core.resolve_channel("veto.akamaized.net", "vglive-sk-274906") == "India TV"
    assert core.resolve_channel("veto-vod.akamaized.net", ASSETS[0]) == "Veto VOD"
