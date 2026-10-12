import sqlite3

from app.database.backup import create_sqlite_backup


def test_online_backup_includes_committed_wal_rows(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE example (value TEXT NOT NULL)")
    connection.execute("INSERT INTO example VALUES ('committed-in-wal')")
    connection.commit()

    create_sqlite_backup(source, destination)

    with sqlite3.connect(destination) as backup:
        assert backup.execute("SELECT value FROM example").fetchall() == [("committed-in-wal",)]
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    connection.close()
