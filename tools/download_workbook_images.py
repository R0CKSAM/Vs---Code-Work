"""Download workbook URL images into category_name/vod_key.ext; safe to rerun."""
import argparse
import csv
import hashlib
import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openpyxl
from PIL import Image


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip()).rstrip(' .')
    if not value or value in ('.', '..'):
        raise ValueError('Missing category_name or vod_key')
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + value
    return value[:160]


def valid_image(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def download(item, out):
    row, category, key, url, filename = item
    result = dict(row=row, category_name=category, vod_key=key, url=url, file='', status='', error='')
    try:
        folder = out / safe_name(category)
        folder.mkdir(parents=True, exist_ok=True)
        base = folder / filename
        # Resume only verified images. Never overwrite an existing file.
        for ext in ('.webp', '.jpg', '.png', '.gif', '.avif', '.bmp', '.tiff'):
            existing = base.with_name(base.name + ext)
            if existing.exists() and valid_image(existing):
                result.update(file=str(existing), status='already_present')
                return result
        for attempt in range(3):
            try:
                request_url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
                request = urllib.request.Request(request_url, headers={'User-Agent': 'WorkbookImageDownloader/1.0', 'Accept': 'image/*'})
                with urllib.request.urlopen(request, timeout=25) as response:
                    if not response.headers.get('Content-Type', '').lower().startswith('image/'):
                        raise ValueError('Server returned non-image content')
                    data = response.read(25 * 1024 * 1024 + 1)
                if len(data) > 25 * 1024 * 1024:
                    raise ValueError('Image exceeds 25 MB safety limit')
                with Image.open(io.BytesIO(data)) as image:
                    fmt = image.format
                    image.verify()
                ext = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'GIF': '.gif', 'AVIF': '.avif', 'BMP': '.bmp', 'TIFF': '.tiff'}.get(fmt)
                if not ext:
                    raise ValueError(f'Unsupported image format: {fmt}')
                target = base.with_name(base.name + ext)
                if target.exists():
                    raise FileExistsError(f'Existing file was not overwritten: {target}')
                tmp = target.with_name(target.name + '.part')
                try:
                    with tmp.open('xb') as handle:
                        handle.write(data)
                    # Windows rename refuses to overwrite an existing destination.
                    tmp.rename(target)
                finally:
                    tmp.unlink(missing_ok=True)
                result.update(file=str(target), status='downloaded')
                return result
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                permanent_http = isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code not in (408, 429)
                if attempt == 2 or isinstance(exc, FileExistsError) or permanent_http:
                    raise
                time.sleep(attempt + 1)
    except Exception as exc:
        result.update(status='failed', error=str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    out = args.out or args.workbook.parent / (args.workbook.stem + '_images')
    out.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    items, seen, owners, errors = [], set(), {}, []
    for sheet in workbook:
        rows = iter(sheet.values)
        header = [str(v or '').strip().lower() for v in next(rows, ())]
        if not {'category_name', 'vod_key', 'url'} <= set(header):
            continue
        for number, values in enumerate(rows, 2):
            if not any(v is not None for v in values):
                continue
            row = f'{sheet.title}:{number}'
            category, key, url = (str(values[header.index(name)] or '').strip() for name in ('category_name', 'vod_key', 'url'))
            category = category or '_Uncategorized'
            try:
                category_safe, key_safe = safe_name(category), safe_name(key)
                parsed = urllib.parse.urlsplit(url)
                if parsed.scheme not in ('https', 'http') or not parsed.netloc:
                    raise ValueError('Invalid or missing HTTP image URL')
                identity = (category_safe.casefold(), key_safe.casefold(), url)
                if identity in seen:
                    continue
                seen.add(identity)
                dest = (category_safe.casefold(), key_safe.casefold())
                filename = key_safe
                if dest in owners and owners[dest] != url:
                    filename += '_' + hashlib.sha256(url.encode()).hexdigest()[:10]
                owners.setdefault(dest, url)
                items.append((row, category, key, url, filename))
            except ValueError as exc:
                errors.append(dict(row=row, category_name=category, vod_key=key, url=url, file='', status='failed', error=str(exc)))
    workbook.close()
    if not items and not errors:
        raise SystemExit('No populated sheet contains category_name, vod_key and URL columns.')
    report = out / 'download_report.csv'
    started = time.monotonic()
    counts = {'downloaded': 0, 'already_present': 0, 'failed': len(errors)}
    print(f'OUTPUT: {out}\nUnique downloads: {len(items):,}; invalid rows: {len(errors)}', flush=True)
    with report.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=['row', 'category_name', 'vod_key', 'url', 'file', 'status', 'error'])
        writer.writeheader()
        writer.writerows(errors)
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as pool:
            futures = [pool.submit(download, item, out) for item in items]
            for completed, future in enumerate(as_completed(futures), 1):
                result = future.result()
                writer.writerow(result)
                handle.flush()
                counts[result['status']] += 1
                if completed % 50 == 0 or completed == len(items):
                    print(f'{completed:,}/{len(items):,} | {counts} | {time.monotonic() - started:.0f}s', flush=True)
    print(f'DONE: {counts}\nReport: {report}', flush=True)
    return int(counts['failed'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
