"""Merge one folder's dated PDFs from oldest to newest, preserving page quality."""
import argparse
import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import pymupdf as pdf
import io
import math
from PIL import Image


def compact_images(document, dpi=180, quality=85):
    """Resize images from their displayed page size, then replace only if smaller."""
    images = {}
    for page in document:
        page.clean_contents(sanitize=True)
        for item in page.get_images(full=True):
            xref, mask, width, height = item[:4]
            if mask or item[4] == 1:  # Preserve transparent and monochrome line-art images.
                continue
            placements = page.get_image_rects(xref, transform=True)
            if not placements:
                continue
            entry = images.setdefault(xref, {'page': page, 'width': width, 'height': height, 'scale': 0})
            for rect, matrix in placements:
                # Matrix vectors account for rotation without changing image aspect ratio.
                across = math.hypot(matrix.a, matrix.b)
                down = math.hypot(matrix.c, matrix.d)
                entry['scale'] = max(entry['scale'], across * dpi / 72 / width, down * dpi / 72 / height)
    replaced = 0
    for n, (xref, info) in enumerate(images.items(), 1):
        raw = document.extract_image(xref)['image']
        with Image.open(io.BytesIO(raw)) as source:
            image = source.convert('RGB')
            factor = min(1, info['scale'])
            size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
            if size != image.size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, format='JPEG', quality=quality, optimize=True)
            encoded = stream.getvalue()
        if len(encoded) < len(raw):
            info['page'].replace_image(xref, stream=encoded)
            replaced += 1
        if n % 10 == 0 or n == len(images):
            print(f'  Optimized {n}/{len(images)} images', flush=True)
    # replace_image adds a temporary resource reference. Remove unused copies before saving.
    for page in document:
        page.clean_contents(sanitize=True)
    return replaced


def collect(folder):
    items, ignored, seen = [], [], {}
    for path in Path(folder).glob('*.pdf'):
        if path.name.startswith('MERGED_'):
            continue
        match = re.search(r'(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)', path.stem)
        if not match:
            ignored.append(path.name)
            continue
        day = date.fromisoformat(match[1])
        if day in seen:
            raise ValueError(f'Two PDFs have date {day}: {seen[day].name} and {path.name}. Choose a folder containing one edition/copy per date.')
        seen[day] = path
        items.append((day, path))
    if not items:
        raise ValueError('No dated PDFs found. Filenames must contain YYYY-MM-DD. Select the actual newspaper or SPORTS_ONLY folder.')
    return sorted(items), ignored


def merge(folder, requested_output=None, compact=False):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f'Folder not found: {folder}')
    items, ignored = collect(folder)
    suffix = '_COMPACT' if compact else ''
    requested = Path(requested_output).resolve() if requested_output else folder / 'MERGED' / f'MERGED_{items[0][0]}_to_{items[-1][0]}{suffix}.pdf'
    if requested.suffix.lower() != '.pdf':
        raise ValueError('Output filename must end in .pdf.')
    if any(requested == p.resolve() for _, p in items):
        raise ValueError('Output cannot replace an input PDF.')
    requested.parent.mkdir(parents=True, exist_ok=True)
    target = requested
    n = 0
    while True:
        try:
            target.open('xb').close()
            break
        except FileExistsError:
            n += 1
            target = requested.with_name(f'{requested.stem}_{n}.pdf')
    rows, toc = [], []
    started = time.monotonic()
    temp = None
    try:
        with pdf.open() as output:
            for i, (day, path) in enumerate(items, 1):
                stat = path.stat()
                print(f'{i}/{len(items)}: {day} — {path.name}', flush=True)
                with path.open('rb') as handle:
                    handle.seek(max(0, stat.st_size - 2048))
                    if b'%%EOF' not in handle.read():
                        raise ValueError(f'Incomplete PDF: {path.name}. Wait for its download to finish.')
                with pdf.open(path) as source:
                    if source.needs_pass or not len(source):
                        raise ValueError(f'Locked or empty PDF: {path.name}')
                    first = len(output) + 1
                    output.insert_pdf(source)
                    rows.append({'date': str(day), 'file': path.name, 'first_page': first, 'last_page': len(output), 'pages': len(source)})
                    toc.append([1, str(day), first])
                after = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError(f'{path.name} changed during merging. Wait for processing to finish.')
            output.set_toc(toc)
            output.set_metadata({'title': f'Newspapers {items[0][0]} to {items[-1][0]}', 'subject': 'Merged in ascending filename date order'})
            if compact:
                print('Creating smaller viewing copy (180 DPI, JPEG quality 85). Original files are unchanged.', flush=True)
                compact_images(output)
            fd, name = tempfile.mkstemp(prefix='.merging_', suffix='.pdf', dir=target.parent)
            os.close(fd)
            temp = Path(name)
            print(f'Writing {len(output)} pages…', flush=True)
            output.save(temp, garbage=4, deflate=True)
        with pdf.open(temp) as check:
            if len(check) != sum(r['pages'] for r in rows):
                raise ValueError('Merged page count did not match inputs.')
        os.replace(temp, target)
        with target.with_suffix('.csv').open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=['date', 'file', 'first_page', 'last_page', 'pages'])
            writer.writeheader()
            writer.writerows(rows)
        days = {d for d, _ in items}
        missing = [str(items[0][0] + timedelta(days=i)) for i in range((items[-1][0] - items[0][0]).days + 1) if items[0][0] + timedelta(days=i) not in days]
        target.with_suffix('.json').write_text(json.dumps({'files': len(items), 'pages': sum(r['pages'] for r in rows), 'missing_dates_between_first_and_last': missing, 'ignored_undated_files': ignored, 'compact': compact, 'image_dpi': 180 if compact else None, 'jpeg_quality': 85 if compact else None, 'output_bytes': target.stat().st_size, 'seconds': round(time.monotonic()-started, 1)}, indent=2), encoding='utf-8')
        print(f'SAVED: {target}\n{len(items)} PDFs merged, {sum(r["pages"] for r in rows)} pages.', flush=True)
        if missing:
            print('Missing dates (not included): ' + ', '.join(missing), flush=True)
        if ignored:
            print('Ignored undated files: ' + ', '.join(ignored), flush=True)
        return target
    except BaseException:
        if temp:
            temp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compact', action='store_true', help='Create a smaller 180-DPI JPEG viewing copy; originals stay unchanged.')
    args = parser.parse_args()
    interactive = not args.folder
    if interactive:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        args.folder = filedialog.askdirectory(title='Select one edition folder, or its SPORTS_ONLY folder', initialdir=r'C:\Users\Intern\Downloads\Storyboard Studio\InduPaper\delhi')
        root.destroy()
        if not args.folder:
            return 0
    result = 0
    try:
        merge(args.folder, args.output, compact=args.compact)
    except Exception as error:
        print(f'ERROR: {error}', flush=True)
        result = 1
    if interactive:
        input('Press Enter to close...')
    return result


if __name__ == '__main__':
    sys.exit(main())
