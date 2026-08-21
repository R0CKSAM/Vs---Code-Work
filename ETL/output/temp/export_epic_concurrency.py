from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "watch_hours" / "concurrency" / "concurrency_minute.parquet"
OUT = ROOT / "output" / "exports" / "epic_concurrency"
START = "2026-07-10"
END_EXCLUSIVE = "2026-08-20"
END_LABEL = "2026-08-19"
CHANNELS = [
    "Epic TV",
    "Epic Bharat",
    "Epic Bhojpuri",
    "Epic Kids",
    "Epic Music",
]
CHANNEL_BY_ID = {
    "epic_tv": "Epic TV",
    "epic_bharat": "Epic Bharat",
    "epic_bhojpuri": "Epic Bhojpuri",
    "epic_kids": "Epic Kids",
    "epic_music": "Epic Music",
}


def sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing concurrency mart: {INPUT}")

    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / f"epic_concurrency_{START}_to_{END_LABEL}.csv"

    source = f"read_parquet('{sql_path(INPUT)}')"
    channel_list = ", ".join(f"'{value}'" for value in CHANNELS)
    candidate_list = ", ".join(f"'{value}'" for value in CHANNEL_BY_ID)
    channel_case = "CASE lower(candidate_id) " + " ".join(
        f"WHEN '{candidate}' THEN '{channel}'"
        for candidate, channel in CHANNEL_BY_ID.items()
    ) + " ELSE channel_name END"
    epic_filter = (
        f"(lower(candidate_id) IN ({candidate_list}) "
        f"OR channel_name IN ({channel_list}))"
    )
    date_filter = (
        f"CAST(minute_ist AS TIMESTAMP) >= TIMESTAMP '{START} 00:00:00' "
        f"AND CAST(minute_ist AS TIMESTAMP) < TIMESTAMP '{END_EXCLUSIVE} 00:00:00'"
    )

    con = duckdb.connect()
    con.execute("SET threads = 8")
    con.execute("SET memory_limit = '8GB'")

    wide_query = f"""
        WITH minutes AS (
            SELECT minute::TIMESTAMP AS minute_ist
            FROM GENERATE_SERIES(
                TIMESTAMP '{START} 00:00:00',
                TIMESTAMP '{END_EXCLUSIVE} 00:00:00' - INTERVAL 1 MINUTE,
                INTERVAL 1 MINUTE
            ) AS generated(minute)
        ),
        epic AS (
            SELECT
                CAST(minute_ist AS TIMESTAMP) AS minute_ist,
                {channel_case} AS channel_name,
                GREATEST(1, ROUND(SUM(segment_viewers_estimate)))::BIGINT
                    AS concurrency
            FROM {source}
            WHERE {date_filter}
              AND {epic_filter}
            GROUP BY ALL
        )
        SELECT
            minutes.minute_ist,
            CAST(minutes.minute_ist AS DATE) AS log_date,
            MAX(CASE WHEN epic.channel_name = 'Epic TV'
                THEN epic.concurrency END)::BIGINT AS "Epic TV",
            MAX(CASE WHEN epic.channel_name = 'Epic Bharat'
                THEN epic.concurrency END)::BIGINT AS "Epic Bharat",
            MAX(CASE WHEN epic.channel_name = 'Epic Bhojpuri'
                THEN epic.concurrency END)::BIGINT AS "Epic Bhojpuri",
            MAX(CASE WHEN epic.channel_name = 'Epic Kids'
                THEN epic.concurrency END)::BIGINT AS "Epic Kids",
            MAX(CASE WHEN epic.channel_name = 'Epic Music'
                THEN epic.concurrency END)::BIGINT AS "Epic Music",
            SUM(epic.concurrency)::BIGINT AS "All Epic Channels"
        FROM minutes
        LEFT JOIN epic USING (minute_ist)
        GROUP BY minutes.minute_ist
        ORDER BY minutes.minute_ist
    """
    con.execute(
        f"COPY ({wide_query}) TO '{sql_path(output)}' "
        "(HEADER, DELIMITER ',', QUOTE '\"', ESCAPE '\"', NULL '')"
    )

    validation = con.execute(
        f"""
        SELECT
            COUNT(*) AS minute_rows,
            MIN(minute_ist) AS first_minute,
            MAX(minute_ist) AS last_minute,
            COUNT(DISTINCT log_date) AS dates,
            COUNT(*) FILTER (WHERE "All Epic Channels" IS NULL) AS blank_all_minutes
        FROM ({wide_query})
        """
    ).fetchone()
    if validation[0] != 59040 or validation[3] != 41:
        raise RuntimeError(f"Unexpected EPIC export coverage: {validation}")
    print(f"output={output}")
    print(
        "minute_rows=%s first=%s last=%s dates=%s blank_all_minutes=%s"
        % validation
    )
    con.close()


if __name__ == "__main__":
    main()
