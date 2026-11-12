"""Create searchable and text-only PDFs plus UTF-8 text using local Windows OCR."""
import argparse
import base64
import csv
import ctypes
import hashlib
import json
import msvcrt
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import queue
import threading
import pymupdf as pdf

BASE = Path(__file__).resolve().parent
FONT = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'arial.ttf'


def atomic(path, data):
    temp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


class WindowsOCR:
    def __init__(self):
        self.process = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(BASE / 'windows_ocr.ps1')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        self.responses = queue.Queue()
        def collect():
            try:
                for line in self.process.stdout:
                    self.responses.put(line)
            finally:
                self.responses.put(None)
        self.reader = threading.Thread(target=collect, daemon=True)
        self.reader.start()
        try:
            self.max_dimension = self.request({'action': 'capabilities'})['max_dimension']
        except BaseException:
            self.close()
            raise

    def request(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()
        try:
            line = self.responses.get(timeout=60)
        except queue.Empty:
            self.process.terminate()
            raise TimeoutError('Windows OCR did not respond within 60 seconds. Rerun to resume cached pages.')
        if not line:
            raise RuntimeError('Windows OCR stopped: ' + self.process.stderr.read()[-1500:])
        data = json.loads(base64.b64decode(line).decode('utf-8'))
        if not data.get('ok'):
            raise RuntimeError(data.get('error', 'Windows OCR failed'))
        return data

    def read(self, image):
        return self.request({'path': str(image)})

    def close(self):
        if self.process.poll() is None:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        for stream in [self.process.stdout, self.process.stderr]:
            if stream:
                stream.close()


def page_dates(source, total):
    result = [{'date': 'Unknown date', 'newspaper_page': None} for _ in range(total)]
    index = source.with_suffix('.csv')
    if not index.exists():
        return result
    with index.open(encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            extra = source.parent.parent / row['file']
            try:
                details = json.loads(extra.with_suffix('.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                details = {}
            for offset, number in enumerate(range(int(row['first_page']), int(row['last_page']) + 1)):
                if 1 <= number <= total:
                    originals = details.get('source_pages', [])
                    result[number-1] = {'date': row['date'], 'newspaper_page': originals[offset] if offset < len(originals) else None}
    return result


def add_text(page, lines, scale, font, invisible):
    page.insert_font(fontname='OCRArial', fontfile=str(FONT))
    shape = page.new_shape()
    inserted = 0
    for line in lines:
        words = line.get('words') or []
        text = line.get('text', '').strip()
        if not words or not text:
            continue
        x = max(0, min(w['x'] for w in words) / scale)
        y = max(0, min(w['y'] for w in words) / scale)
        right = min(page.rect.width, max(w['x']+w['width'] for w in words) / scale)
        bottom = min(page.rect.height, max(w['y']+w['height'] for w in words) / scale)
        width, height = right-x, bottom-y
        if width <= 0 or height <= 0:
            continue
        size = max(2, min(36, height / (font.ascender-font.descender)))
        baseline = min(page.rect.height-1, y+font.ascender*size)
        natural = font.text_length(text, fontsize=size)
        if natural <= 0:
            continue
        origin = pdf.Point(x, baseline)
        shape.insert_text(origin, text, fontname='OCRArial', fontsize=size,
                          render_mode=3 if invisible else 0,
                          morph=(origin, pdf.Matrix(width/natural, 1)))
        inserted += len(text)
    shape.commit()
    return inserted


def normalize_text_maps(document):
    # Arial shares glyphs for space/NBSP and hyphen/soft-hyphen. Prefer normal
    # characters so scores such as 3-1 survive extraction by independent PDF readers.
    references = {f[0] for page in document for f in page.get_fonts() if f[4] == 'OCRArial'}
    for reference in references:
        kind, value = document.xref_get_key(reference, 'ToUnicode')
        if kind != 'xref':
            continue
        xref = int(value.split()[0])
        mapping = document.xref_stream(xref)
        for old, new in [(b'00a0', b'0020'), (b'00ad', b'002d')]:
            mapping = re.sub(rb'(?im)^(<[0-9a-f]+>[ \t]+)<' + old + rb'>[ \t]*$',
                             lambda match: match[1] + b'<' + new + b'>', mapping)
        document.update_stream(xref, mapping)


def run(source, visual=None, output=None, dpi=240):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError(f'PDF not found: {source}')
    if not FONT.exists():
        raise ValueError('Windows Arial font not found.')
    visual = Path(visual).resolve() if visual else source.with_name(source.stem+'_COMPACT.pdf')
    if not visual.exists():
        visual = source
    output = Path(output).resolve() if output else source.parent / 'AI_OCR'
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / 'ocr.lock').open('a+b')
    lock.seek(0)
    if lock.read(1) == b'':
        lock.write(b'0'); lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    stat = source.stat()
    settings = {'source': str(source), 'size': stat.st_size, 'mtime': stat.st_mtime_ns, 'dpi': dpi, 'engine': 'Windows.Media.Ocr-en-US-v2'}
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
    cache = output / ('cache_'+key)
    cache.mkdir(exist_ok=True)
    started = time.monotonic()
    engine = None
    results = []
    total = 0

    def progress(phase, done, total, **extra):
        elapsed = time.monotonic()-started
        data = {'phase': phase, 'source': str(source), 'completed_pages': done, 'total_pages': total,
                'elapsed_seconds': round(elapsed, 1), 'estimated_remaining_seconds': round(elapsed/done*(total-done)) if done else None,
                'updated': time.strftime('%Y-%m-%dT%H:%M:%S'), 'pid': os.getpid(), **extra}
        atomic(output / 'progress.json', data)
        atomic(BASE / 'ocr_status.json', data)

    try:
        with pdf.open(source) as document:
            if document.needs_pass:
                raise ValueError('Unlock this PDF before OCR.')
            total = len(document)
            dates = page_dates(source, total)
            print(f'LOCAL OCR: {source.name}\n{total} pages. Cache and outputs: {output}', flush=True)
            progress('ocr', 0, total)
            for i, page in enumerate(document):
                saved = cache / f'page_{i+1:04d}.json'
                if saved.exists():
                    data = json.loads(saved.read_text(encoding='utf-8'))
                else:
                    if engine is None:
                        engine = WindowsOCR()
                    scale = min(dpi/72, (engine.max_dimension-50)/max(page.rect.width, page.rect.height))
                    image = cache / f'page_{i+1:04d}.png'
                    page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False).save(image)
                    data = engine.read(image)
                    data['scale'] = scale
                    atomic(saved, data)
                    image.unlink(missing_ok=True)
                data['attribution'] = dates[i]
                results.append(data)
                chars = sum(len(line.get('text','')) for line in data.get('lines', []))
                print(f'OCR {i+1}/{total}: {len(data.get("lines",[]))} lines, {chars} characters, date {dates[i]["date"]}', flush=True)
                progress('ocr', i+1, total, last_page_characters=chars)
            if source.stat().st_size != stat.st_size or source.stat().st_mtime_ns != stat.st_mtime_ns:
                raise ValueError('Source changed during OCR; rerun with its new version.')
        if engine:
            engine.close(); engine = None
        progress('building_pdfs', total, total)
        stem = source.stem
        targets = {'searchable_pdf': output / f'{stem}_SEARCHABLE.pdf', 'text_pdf': output / f'{stem}_AI_TEXT.pdf', 'text': output / f'{stem}_AI_TEXT.txt'}
        font = pdf.Font(fontfile=str(FONT))
        warnings = []
        with pdf.open(visual) as searchable, pdf.open() as text_pdf:
            if len(searchable) != total:
                raise ValueError('Visual PDF has a different page count from the OCR source.')
            with pdf.open(source) as geometry:
                if any(geometry[i].rect != searchable[i].rect for i in range(total)):
                    raise ValueError('Visual PDF page sizes differ from the OCR source.')
            text_parts = [f'OCR TRANSCRIPTION - {stem}\nRecognized locally from newspaper scans. OCR may misread names, scores and column order; compare important details with the searchable image PDF.\n']
            for i, data in enumerate(results):
                date = data['attribution']['date']
                original = data['attribution']['newspaper_page']
                heading = f'Date: {date} | Merged PDF page: {i+1}' + (f' | Newspaper PDF page: {original}' if original else '')
                visual_page = searchable[i]
                clean_page = text_pdf.new_page(width=visual_page.rect.width, height=visual_page.rect.height)
                for target, hidden in [(visual_page, True), (clean_page, False)]:
                    target.insert_font(fontname='OCRArial', fontfile=str(FONT))
                    target.insert_text((5, 8), heading, fontname='OCRArial', fontsize=6, render_mode=3 if hidden else 0)
                    chars = add_text(target, data.get('lines', []), data['scale'], font, hidden)
                if chars < 200:
                    warnings.append({'merged_page': i+1, 'date': date, 'reason': 'Less than 200 OCR characters; review this page.'})
                text_parts.extend(['\n\n=== '+heading+' ===\n', '\n'.join(line.get('text','') for line in data.get('lines', []))])
            text_pdf.set_toc(searchable.get_toc())
            for doc in [searchable, text_pdf]:
                doc.set_metadata({'title': stem+' - OCR', 'subject': 'Local OCR transcription; compare important details with source newspaper.'})
                doc.subset_fonts()
                normalize_text_maps(doc)
            for kind, doc in [('searchable_pdf', searchable), ('text_pdf', text_pdf)]:
                temp = targets[kind].with_suffix('.building.pdf')
                doc.save(temp, garbage=4, deflate=True)
                with pdf.open(temp) as check:
                    if len(check) != total or any(len(page.get_text().strip()) < 20 for page in check):
                        raise ValueError(f'{kind} did not contain extractable text on every page.')
                os.replace(temp, targets[kind])
            targets['text'].write_text('\n'.join(text_parts), encoding='utf-8')
        atomic(output / 'ocr_report.json', {**settings, 'pages': total, 'warnings': warnings,
               'outputs': {key: str(value) for key,value in targets.items()}, 'seconds': round(time.monotonic()-started, 1)})
        progress('complete', total, total, outputs={k: str(v) for k,v in targets.items()}, review_pages=warnings)
        print('COMPLETE\n'+'\n'.join(str(p) for p in targets.values()), flush=True)
        return targets
    except BaseException as error:
        progress('stopped', len(results), total, error=str(error))
        raise
    finally:
        if engine:
            engine.close()
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?')
    parser.add_argument('--visual')
    parser.add_argument('--out-dir')
    parser.add_argument('--dpi', type=int, default=240)
    args = parser.parse_args()
    if not args.source:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw()
        args.source=filedialog.askopenfilename(title='Choose merged newspaper PDF to OCR',filetypes=[('PDF','*.pdf')])
        root.destroy()
    if args.source:
        run(args.source, args.visual, args.out_dir, args.dpi)
