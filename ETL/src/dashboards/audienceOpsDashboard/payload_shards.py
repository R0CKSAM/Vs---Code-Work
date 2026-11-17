"""Publish bounded local JS payloads instead of a browser-sized inline script."""
import json
from pathlib import Path
import uuid


def write_payload_shards(data, output: Path):
    folder = output.parent / (output.stem + '_data_' + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    paths, lines, size = [], [], 0
    def flush():
        nonlocal lines, size
        if lines:
            path = folder / f'{len(paths):04d}.js'
            path.write_text('\n'.join(lines), encoding='utf-8')
            paths.append(path)
            lines, size = [], 0
    def emit(line):
        nonlocal size
        if size + len(line) > 4 * 1024 * 1024:
            flush()
        lines.append(line)
        size += len(line)
    def encode(value):
        return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    def visit(value, target):
        if isinstance(value, dict):
            emit(target + '={};')
            for key, item in value.items():
                visit(item, target + '[' + encode(key) + ']')
        elif isinstance(value, list):
            emit(target + '=[];')
            batch, length = [], 0
            for item in value:
                encoded = encode(item)
                if batch and (length + len(encoded) > 1024 * 1024 or len(batch) >= 500):
                    emit(target + '.push(' + ','.join(batch) + ');')
                    batch, length = [], 0
                batch.append(encoded)
                length += len(encoded)
            if batch:
                emit(target + '.push(' + ','.join(batch) + ');')
        else:
            emit(target + '=' + encode(value) + ';')
    visit(data, 'window.__AUDIENCE_DATA__')
    flush()
    return '\n'.join(f'<script src="{folder.name}/{p.name}"></script>' for p in paths)
