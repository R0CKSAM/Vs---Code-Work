"""Read-only best-effort SQLite table B-tree walker.
No sqlite3 connection, writes, WAL checkpoint, database reconstruction, or SQL queries.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import struct

class PageError(Exception):
    pass

@dataclass
class Table:
    name: str
    root: int
    sql: str


def varint(buf: bytes, pos: int):
    val = 0
    for i in range(9):
        if pos >= len(buf): raise PageError('short varint')
        b = buf[pos]; pos += 1
        if i == 8: return (val << 8) | b, pos
        val = (val << 7) | (b & 127)
        if b < 128: return val, pos
    raise PageError('invalid varint')


def record(payload: bytes, encoding='utf-8'):
    head, pos = varint(payload, 0)
    if head > len(payload) or head < pos: raise PageError('invalid record header')
    serials = []
    while pos < head:
        typ, pos = varint(payload, pos)
        serials.append(typ)
    if pos != head: raise PageError('record header alignment')
    pos = head
    values=[]
    for typ in serials:
        if typ == 0: values.append(None); continue
        if typ == 8: values.append(0); continue
        if typ == 9: values.append(1); continue
        if typ in (10,11): raise PageError('reserved serial type')
        sizes = {1:1,2:2,3:3,4:4,5:6,6:8,7:8}
        n = sizes[typ] if typ in sizes else (typ-12)//2
        if n < 0 or pos + n > len(payload): raise PageError('short field')
        raw = payload[pos:pos+n]; pos += n
        if typ in sizes and typ != 7: val = int.from_bytes(raw,'big',signed=True)
        elif typ == 7: val = struct.unpack('>d', raw)[0]
        elif typ % 2 == 0: val = raw
        else: val = raw.decode(encoding, errors='replace')
        values.append(val)
    return values

class RawSQLite:
    def __init__(self, filename, max_cell_bytes=8*1024*1024):
        self.path=Path(filename)
        self.fp=None
        self.max_cell_bytes=max_cell_bytes
        self.stats=Counter()
    def __enter__(self):
        self.fp=self.path.open('rb')
        hdr=self.fp.read(100)
        if hdr[:16] != b'SQLite format 3\x00': raise PageError('Not a SQLite3 file')
        self.page_size=int.from_bytes(hdr[16:18],'big')
        if self.page_size==1: self.page_size=65536
        self.usable=self.page_size-hdr[20]
        self.page_count=self.path.stat().st_size//self.page_size
        enc=int.from_bytes(hdr[56:60],'big')
        self.encoding={1:'utf-8',2:'utf-16-le',3:'utf-16-be'}.get(enc,'utf-8')
        self.stats.clear()
        return self
    def __exit__(self,*exc):
        if self.fp: self.fp.close()
    def page(self,n):
        if not 1 <= n <= self.page_count: raise PageError(f'page outside file: {n}')
        self.fp.seek((n-1)*self.page_size)
        b=self.fp.read(self.page_size)
        if len(b)!=self.page_size: raise PageError('short page')
        return b
    def u16(self,b,p):
        if p+2>len(b): raise PageError('short u16')
        return int.from_bytes(b[p:p+2],'big')
    def u32(self,b,p):
        if p+4>len(b): raise PageError('short u32')
        return int.from_bytes(b[p:p+4],'big')
    def cell_payload(self,page, pos):
        size,p=varint(page,pos)
        rowid,p=varint(page,p)
        if size>self.max_cell_bytes:
            self.stats['oversized_records']+=1
            raise PageError('record exceeds configured limit')
        max_local=self.usable-35
        min_local=((self.usable-12)*32//255)-23
        if size<=max_local: local=size
        else:
            local=min_local + (size-min_local)%(self.usable-4)
            if local>max_local: local=min_local
        if p+local>len(page): raise PageError('cell outside page')
        data=bytearray(page[p:p+local])
        if local<size:
            overflow=self.u32(page,p+local)
            visited=set()
            while len(data)<size:
                if not overflow or overflow in visited: raise PageError('overflow cycle or missing link')
                visited.add(overflow)
                fragment=self.page(overflow)
                self.stats['overflow_pages']+=1
                take=min(size-len(data),self.usable-4)
                data.extend(fragment[4:4+take])
                overflow=self.u32(fragment,0)
        return rowid,record(bytes(data),self.encoding)
    def scan_table(self, root, max_pages=50000, max_rows=100000, stop=None):
        """Yields (rowid, values). DFS B-tree traversal, skips malformed cells/pages.
        stop(): true interrupts work. Counters in self.stats are cumulative for the scan.
        """
        todo=[root]; seen=set(); emitted=0
        while todo and len(seen)<max_pages and emitted<max_rows:
            if stop and stop(): break
            n=todo.pop()
            if n in seen: continue
            seen.add(n)
            try:
                pg=self.page(n)
                off=100 if n==1 else 0
                kind=pg[off]
                if kind not in (5,13): raise PageError(f'unexpected page type {kind}')
                count=self.u16(pg,off+3)
                headerlen=12 if kind==5 else 8
                if count*2+off+headerlen>self.usable: raise PageError('impossible cell count')
                self.stats['btree_pages']+=1
                ptrs=[]
                for i in range(count):
                    ptr=self.u16(pg,off+headerlen+i*2)
                    if not off+headerlen <= ptr < self.usable: raise PageError('bad cell pointer')
                    ptrs.append(ptr)
                if kind==5:
                    children=[self.u32(pg,p) for p in ptrs]
                    children.append(self.u32(pg,off+8))
                    todo.extend(reversed(children))
                else:
                    for ptr in ptrs:
                        if stop and stop(): return
                        try:
                            rowid,row=self.cell_payload(pg,ptr)
                            self.stats['rows_read']+=1
                            emitted+=1
                            yield rowid,row
                            if emitted>=max_rows: return
                        except (PageError, ValueError, OverflowError, UnicodeError, struct.error):
                            self.stats['bad_cells']+=1
            except (PageError, ValueError, IndexError):
                self.stats['bad_pages']+=1
        if todo and len(seen)>=max_pages: self.stats['page_limit_hit']+=1
        if todo and emitted>=max_rows: self.stats['row_limit_hit']+=1
    def tables(self):
        result=[]
        for _,r in self.scan_table(1,max_pages=5000,max_rows=10000):
            if len(r)>=5 and r[0]=='table' and isinstance(r[1],str) and isinstance(r[3],int):
                result.append(Table(r[1],r[3],r[4] or ''))
        return result
