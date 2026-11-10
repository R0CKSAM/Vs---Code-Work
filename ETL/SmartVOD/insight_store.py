"""Compact columnar projection for insight queries, bound to one source snapshot."""
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime
import json,os,re,sqlite3

ROOT=Path(__file__).resolve().parent
COLUMNS=['day','clock','title','category','video_key','device_id','cli_ip','os','region','isp','device_type','identity_confidence','title_status','hours','segments','req_host','delivered','raw_title','request_ist']
SCHEMA=3
def fingerprint(path):
    stat=path.stat();return dict(path=str(path.resolve()),size=stat.st_size,mtime_ns=stat.st_mtime_ns)
class Row(Mapping):
    def __init__(self,names,values):self.names=names;self.values=values
    def __getitem__(self,key):return self.values[key] if isinstance(key,int) else self.values[self.names.index(key)]
    def __iter__(self):return iter(self.names)
    def __len__(self):return len(self.names)
class Result:
    def __init__(self,cursor):
        self.description=cursor.description;names=[c[0] for c in self.description];self.rows=[Row(names,row) for row in cursor.fetchall()]
    def __iter__(self):return iter(self.rows)
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows
class Connection:
    columnar=True
    def __init__(self,connection):self.connection=connection
    def execute(self,sql,params=None):return Result(self.connection.execute(re.sub(r' INDEXED BY idx_\w+','',sql),params or []))

@contextmanager
def analytical_connection(factory):
    with factory() as original:
        source=Path(original.execute('PRAGMA database_list').fetchone()[2])
        manifest=ROOT/'data/insight_store.json'
        try:
            info=json.loads(manifest.read_text());database=ROOT/'data'/info['database']
            valid=info.get('schema')==SCHEMA and info['source']==fingerprint(source) and database.is_file()
        except (OSError,ValueError,KeyError):valid=False
        if not valid:yield original;return
        import duckdb
        con=duckdb.connect(str(database),read_only=True,config={'threads':2,'memory_limit':'1GB'})
        try:yield Connection(con)
        finally:con.close()

def build(root=ROOT):
    folder=root/'data';folder.mkdir(exist_ok=True);lock=(folder/'insight_store.lock').open('a+')
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write('0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _build(root)
    finally:lock.close()
def _build(root):
    import duckdb,pyarrow as pa
    folder=root/'data';metadata=json.loads((folder/'manifest.json').read_text());source=folder/metadata['database'];signature=fingerprint(source)
    manifest=folder/'insight_store.json'
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if old.get('schema')==SCHEMA and old.get('source')==signature and (folder/old['database']).is_file():print('Analysis store is current.',flush=True);return old
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');output=folder/f'insights_{stamp}.duckdb'
    original=sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True)
    con=duckdb.connect(str(output),config={'threads':2,'memory_limit':'1GB'});count=0;complete=False
    try:
        cursor=original.execute('SELECT '+','.join(COLUMNS)+' FROM events')
        types=[pa.float64() if name in {'hours','delivered'} else pa.int64() if name=='segments' else pa.string() for name in COLUMNS]
        while True:
            rows=cursor.fetchmany(25000)
            if not rows:break
            arrays=[pa.array(values,type=kind) for values,kind in zip(zip(*rows),types)]
            table=pa.Table.from_arrays(arrays,names=COLUMNS);con.register('source_batch',table)
            if not count:con.execute('CREATE TABLE events AS SELECT * FROM source_batch WHERE false')
            con.execute('INSERT INTO events SELECT * FROM source_batch');con.unregister('source_batch');count+=len(rows)
            if count%500000==0:print(f'Projected {count:,} rows',flush=True)
        if not count:raise ValueError('No source rows available')
        check=con.execute('SELECT count(*),sum(hours),sum(segments) FROM events').fetchone()
        if check[0]!=metadata['records'] or abs(check[1]-metadata['hours'])>1e-5 or check[2]!=metadata['segments']:raise ValueError('Projection totals do not match source manifest')
        if fingerprint(source)!=signature:raise RuntimeError('Source snapshot changed while building analysis store')
        if json.loads((folder/'manifest.json').read_text())['database']!=source.name:raise RuntimeError('A newer dashboard snapshot was published during analysis build')
        con.execute('CHECKPOINT')
        complete=True
    finally:
        con.close();original.close()
        if not complete:
            try:output.unlink()
            except OSError:pass
    info=dict(schema=SCHEMA,database=output.name,source=signature,records=count,built_at=datetime.now().isoformat(),hours=check[1],segments=check[2])
    pending=manifest.with_suffix('.pending.json');pending.write_text(json.dumps(info,indent=2));pending.replace(manifest)
    versions=sorted(folder.glob('insights_*.duckdb'),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in versions[2:]:
        if old==output:continue
        try:old.unlink()
        except OSError:pass
    print(f'Published analysis store: {count:,} rows / {output.stat().st_size/1024**2:.1f} MiB',flush=True);return info
if __name__=='__main__':build()
