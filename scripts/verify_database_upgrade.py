"""Migrate a working database; compare every original column and run SQLite checks.
Run with server stopped. Never operate on the only copy.
"""
from pathlib import Path
import json
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.database import init_engine, create_all


def snapshot(path):
    with sqlite3.connect(path) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_migrations'")]
        return {t: ([r[1] for r in db.execute(f'PRAGMA table_info("{t}")')], db.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall()) for t in tables}


def upgrade(path):
    original = snapshot(path)
    engine = init_engine('sqlite:///' + str(path.resolve()), force=True)
    create_all()
    engine.dispose()
    with sqlite3.connect(path) as db:
        for table, (columns, rows) in original.items():
            fields = ','.join('"'+c+'"' for c in columns)
            assert db.execute(f'SELECT {fields} FROM "{table}" ORDER BY 1').fetchall() == rows, table
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        version = db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0]
    return {'integrity':'ok','foreign_keys':'ok','original_values_preserved':True,'schema_version':version,'original_counts':{t:len(r) for t,(_c,r) in original.items()}}

if __name__ == '__main__':
    print(json.dumps(upgrade(Path(sys.argv[1])),ensure_ascii=False,indent=2))
