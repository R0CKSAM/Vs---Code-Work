
from pathlib import Path
import struct

DB = Path(r"D:\live_monitor.sqlite3")
PAGE_SIZE = 4096
MAX_PAGES = 10000

def varint(data, pos):
    value = 0
    for i in range(9):
        if pos >= len(data):
            raise ValueError("Incomplete varint")
        b = data[pos]
        pos += 1
        if i == 8:
            return (value << 8) | b, pos
        value = (value << 7) | (b & 127)
        if b < 128:
            return value, pos
    raise ValueError("Invalid varint")

def decode_record(payload):
    header_size, pos = varint(payload, 0)
    if header_size > len(payload):
        raise ValueError("Incomplete record header")

    types = []
    while pos < header_size:
        t, pos = varint(payload, pos)
        types.append(t)

    pos = header_size
    values = []

    for t in types:
        if t == 0:
            values.append(None)
            continue

        sizes = {1:1, 2:2, 3:3, 4:4, 5:6, 6:8, 7:8, 8:0, 9:0}

        if t in (10, 11):
            raise ValueError("Reserved serial type")

        if t == 8:
            values.append(0)
            continue

        if t == 9:
            values.append(1)
            continue

        n = sizes[t] if t <= 7 else (t - 12) // 2

        if pos + n > len(payload):
            raise ValueError("Incomplete record")

        raw = payload[pos:pos+n]
        pos += n

        if 1 <= t <= 6:
            values.append(int.from_bytes(raw, "big", signed=True))
        elif t == 7:
            values.append(struct.unpack(">d", raw)[0])
        elif t % 2 == 0:
            values.append(raw)
        else:
            values.append(raw.decode("utf-8", errors="replace"))

    return values

with open(DB, "rb") as f:
    header = f.read(100)

    if header[:16] != b"SQLite format 3\x00":
        raise ValueError("Not a SQLite database")

    PAGE_SIZE = int.from_bytes(header[16:18], "big")
    if PAGE_SIZE == 1:
        PAGE_SIZE = 65536

    reserved = header[20]
    usable = PAGE_SIZE - reserved
    total_pages = DB.stat().st_size // PAGE_SIZE

    print("Database:", DB)
    print("Page size:", PAGE_SIZE)
    print("Physical pages:", total_pages)
    print("\nREADING TABLE STRUCTURE...\n")

    def read_page(pgno):
        if not 1 <= pgno <= total_pages:
            raise ValueError(f"Page {pgno} outside file")
        f.seek((pgno - 1) * PAGE_SIZE)
        data = f.read(PAGE_SIZE)
        if len(data) != PAGE_SIZE:
            raise ValueError("Incomplete page")
        return data

    def read_table(root, limit=100):
        stack = [root]
        visited = set()
        count = 0

        while stack and count < limit and len(visited) < MAX_PAGES:
            pgno = stack.pop()

            if pgno in visited:
                continue
            visited.add(pgno)

            try:
                page = read_page(pgno)
                offset = 100 if pgno == 1 else 0
                typ = page[offset]
                ncell = int.from_bytes(
                    page[offset+3:offset+5], "big"
                )

                if ncell > PAGE_SIZE // 2:
                    continue

                if typ == 5:
                    right = int.from_bytes(
                        page[offset+8:offset+12], "big"
                    )

                    children = []
                    for i in range(ncell):
                        p = offset + 12 + 2*i
                        cell = int.from_bytes(page[p:p+2], "big")
                        child = int.from_bytes(
                            page[cell:cell+4], "big"
                        )
                        children.append(child)

                    stack.extend(reversed(children + [right]))

                elif typ == 13:
                    for i in range(ncell):
                        p = offset + 8 + 2*i
                        cell = int.from_bytes(page[p:p+2], "big")

                        length, pos = varint(page, cell)
                        rowid, pos = varint(page, pos)

                        # SQLite table leaf local payload size
                        max_local = usable - 35
                        min_local = ((usable - 12) * 32 // 255) - 23

                        if length <= max_local:
                            local = length
                        else:
                            local = min_local + (
                                (length - min_local) % (usable - 4)
                            )
                            if local > max_local:
                                local = min_local

                        # Skip records requiring overflow pages
                        if length > local:
                            continue

                        payload = page[pos:pos+length]
                        if len(payload) != length:
                            continue

                        try:
                            row = decode_record(payload)
                            yield rowid, row
                            count += 1
                            if count >= limit:
                                return
                        except (ValueError, IndexError, struct.error):
                            continue

            except (ValueError, IndexError, struct.error):
                continue

    tables = []

    for rowid, record in read_table(1, limit=10000):
        if len(record) < 5:
            continue

        obj_type, name, tbl_name, rootpage, sql = record[:5]

        if obj_type == "table":
            tables.append((name, rootpage, sql))
            print("=" * 60)
            print("TABLE:", name)
            print("ROOT PAGE:", rootpage)
            print("STRUCTURE:", sql)

    print("\nTOTAL TABLES FOUND:", len(tables))

    print("\nSAMPLE RECORDS:\n")

    for name, rootpage, sql in tables:
        if not isinstance(rootpage, int) or rootpage < 1:
            continue

        print("\nTABLE:", name)

        found = False
        for rowid, values in read_table(rootpage, limit=5):
            print("ROWID:", rowid)
            print("VALUES:", repr(values)[:1000])
            found = True

        if not found:
            print("No directly readable inline rows found")
