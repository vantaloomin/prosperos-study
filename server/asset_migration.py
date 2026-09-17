"""Add persona assets without changing existing identities or version rows."""
import sqlite3


def migrate_asset_kinds(path):
    with sqlite3.connect(path, isolation_level=None) as connection:
        row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='assets'").fetchone()
        if row is None or "'persona'" in row[0]:
            return
        connection.execute('PRAGMA foreign_keys=OFF')
        connection.execute('BEGIN IMMEDIATE')
        try:
            rebuild_assets(connection)
            if connection.execute('PRAGMA foreign_key_check').fetchone():
                raise sqlite3.IntegrityError('Library migration found broken references; no changes were saved.')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def rebuild_assets(connection):
    objects = connection.execute("SELECT sql FROM sqlite_master WHERE tbl_name='assets' "
                                 "AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
    connection.execute("CREATE TABLE assets_with_personas (id TEXT PRIMARY KEY, "
                       "kind TEXT NOT NULL CHECK(kind IN ('character','lorebook','persona')), "
                       "latest_version_id TEXT, created_at TEXT NOT NULL)")
    connection.execute('INSERT INTO assets_with_personas (rowid,id,kind,latest_version_id,created_at) '
                       'SELECT rowid,id,kind,latest_version_id,created_at FROM assets')
    connection.execute('DROP TABLE assets')
    connection.execute('ALTER TABLE assets_with_personas RENAME TO assets')
    for (sql,) in objects:
        connection.execute(sql)
