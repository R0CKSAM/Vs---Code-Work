import duckdb

path = r"ETL/output/watch_hours/concurrency/identity_minute.parquet"
db = duckdb.connect()
print(db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path]).fetchall())
print(db.execute("""
    SELECT log_date, source, minute_ist, distinct_cliips, channel_name, platform_name
    FROM read_parquet(?)
    WHERE log_date = '2026-08-19' AND lower(source) = 'stream'
    ORDER BY minute_ist
    LIMIT 12
""", [path]).fetchall())
print(db.execute("""
    SELECT source, log_date, minute_ist, SUM(distinct_cliips) AS users
    FROM read_parquet(?)
    WHERE log_date = '2026-08-19'
    GROUP BY source, log_date, minute_ist
    ORDER BY users DESC
    LIMIT 10
""", [path]).fetchall())
for identity in [r"ETL/output/watch_hours/concurrency/identity_minute.parquet", r"ETL/output/identity/identity_minute.parquet", r"ETL/output/identity/identity_mart.parquet"]:
    try:
        print(identity, db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [identity]).fetchall())
        print(db.execute("SELECT * FROM read_parquet(?) WHERE log_date='2026-08-19' LIMIT 3", [identity]).fetchall())
    except Exception as exc:
        print(identity, exc)
print(db.execute("""
    SELECT minute_ist, SUM(distinct_cliips) AS users, COUNT(*) AS rows
    FROM read_parquet(?)
    WHERE log_date = '2026-08-19' AND lower(source) = 'stream'
    GROUP BY minute_ist
    ORDER BY users DESC
    LIMIT 10
""", [path]).fetchall())
