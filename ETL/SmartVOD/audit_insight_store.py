"""Projection correctness, adapter compatibility and strict source binding."""
from contextlib import contextmanager
from pathlib import Path
import json,sqlite3,sys,tempfile
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import insight_store
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='smartvod_store_') as temp:
    root=Path(temp);folder=root/'data';folder.mkdir();source=folder/'fixture.sqlite'
    con=sqlite3.connect(source);columns=insight_store.COLUMNS
    con.execute('CREATE TABLE events('+','.join(c+(' REAL' if c in {'hours','delivered'} else ' INTEGER' if c=='segments' else ' TEXT') for c in columns)+')')
    row={c:'Unknown' for c in columns};row.update(day='2026-11-09',clock='12:00',hours=3.0,delivered=3.0,segments=1800,region='IN / A / City',device_id='one')
    con.execute('INSERT INTO events VALUES('+','.join('?' for _ in columns)+')',[row[c] for c in columns]);con.execute('CREATE INDEX idx_day ON events(day)');con.commit();con.close()
    (folder/'manifest.json').write_text(json.dumps(dict(database=source.name,records=1,hours=3,segments=1800)))
    info=insight_store.build(root);check('Projection contains expected rows',info['records']==1)
    check('Projection hours reconcile',info['hours']==3)
    check('Projection segments reconcile',info['segments']==1800)
    check('Exact source fingerprint recorded',info['source']==insight_store.fingerprint(source))
    check('Current projection reused',insight_store.build(root)['database']==info['database'])
    @contextmanager
    def connection():
        c=sqlite3.connect(source);c.row_factory=sqlite3.Row
        try:yield c
        finally:c.close()
    previous=insight_store.ROOT;insight_store.ROOT=root
    try:
        with insight_store.analytical_connection(connection) as con:
            check('Matching source uses columnar backend',getattr(con,'columnar',False))
            result=con.execute('SELECT sum(hours) AS hours FROM events INDEXED BY idx_day WHERE day=?',['2026-11-09']).fetchone()
            check('Adapter supports index-clause removal and parameters',result['hours']==3)
            check('Adapter supports numeric row indexing',result[0]==3)
            check('Adapter rows convert to dictionaries',dict(result)=={'hours':3})
        c=sqlite3.connect(source);c.execute('UPDATE events SET hours=4');c.commit();c.close()
        with insight_store.analytical_connection(connection) as con:
            check('Changed source rejects stale projection',not getattr(con,'columnar',False))
            check('Fallback reads updated source, not stale values',con.execute('SELECT sum(hours) FROM events').fetchone()[0]==4)
    finally:insight_store.ROOT=previous
(ROOT/'audit/insight_store.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'projection and source-binding checks')
