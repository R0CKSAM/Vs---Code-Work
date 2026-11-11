"""Extract newspaper Sports section pages, keeping their original PDF quality."""
import argparse
import csv
import json
from pathlib import Path
import re
import time
import pymupdf as pdf


def sports_heading(text):
    words = re.sub(r'[^A-Z]', '', text.upper())
    return words in {'SPORT', 'SPORTS', 'TIMESSPORT', 'TIMESSPORTS', 'TOISPORTS'}


def extract(path, engine, output=None, pages=None):
    path = Path(path).resolve()
    folder = Path(output or path.parent / 'SPORTS_ONLY')
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records, selected = [], []
    with pdf.open(path) as source:
        if source.needs_pass:
            raise ValueError('Password-protected PDF; unlock it before processing.')
        if pages:
            selected = sorted(set(pages))
            if any(p < 1 or p > len(source) for p in selected):
                raise ValueError(f'Page numbers must be between 1 and {len(source)}.')
        else:
            for i, page in enumerate(source):
                # Only the masthead band is checked. Body mentions of sport do not qualify.
                clip = pdf.Rect(0, 0, page.rect.width, page.rect.height * .115)
                lines = page.get_text('blocks', clip=clip)
                found = [str(block[4]).strip() for block in lines if sports_heading(str(block[4]).strip())]
                snippets = [str(block[4]).strip() for block in lines]
                if not snippets:
                    scale = 1700 / page.rect.width
                    pix = page.get_pixmap(matrix=pdf.Matrix(scale, scale), clip=clip, alpha=False)
                    results, _ = engine(pix.tobytes('png'))
                    snippets = [r[1] for r in results or []]
                    found = [r[1] for r in results or [] if float(r[2]) >= .65 and sports_heading(r[1])]
                match = bool(found)
                if match:
                    selected.append(i + 1)
                records.append({'page': i + 1, 'sports_heading': match, 'heading_text': ' | '.join(snippets)})
                print(f'  {i+1}/{len(source)}: {"SPORTS FOUND" if match else "checked"}', flush=True)
        report = folder / (path.stem + '_scan.csv')
        with report.open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=['page', 'sports_heading', 'heading_text'])
            writer.writeheader()
            writer.writerows(records)
        if not selected:
            print(f'NO SPORTS HEADING FOUND: {path.name}. Check {report.name}; no empty PDF created.', flush=True)
            return None
        n = 0
        while True:
            target = folder / f'{path.stem}_SPORTS{f"_{n}" if n else ""}.pdf'
            try:
                target.open('xb').close()
                break
            except FileExistsError:
                n += 1
        try:
            with pdf.open() as result:
                for number in selected:
                    result.insert_pdf(source, from_page=number - 1, to_page=number - 1)
                # InduPaper shares every edition image in each page's resource dictionary.
                # Drop unused references before garbage collection, without re-encoding images.
                for page in result:
                    page.clean_contents(sanitize=True)
                result.set_metadata({'title': path.stem + ' — Sports', 'subject': 'Original pages: ' + ', '.join(map(str, selected))})
                result.save(target, garbage=4, deflate=True)
            with pdf.open(target) as check:
                assert len(check) == len(selected), 'Output page count mismatch'
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    print(f'SAVED: {target}\n  Original pages: {selected}; elapsed {time.monotonic()-started:.1f}s', flush=True)
    target.with_suffix('.json').write_text(json.dumps({'source': str(path), 'source_pages': selected, 'output': str(target), 'seconds': round(time.monotonic()-started, 1)}, indent=2), encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', help='PDF files or folders (non-recursive)')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--pages', help='Manual page numbers, e.g. 21,22. Bypasses OCR.')
    args = parser.parse_args()
    interactive = not args.inputs
    if interactive:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        args.inputs = list(filedialog.askopenfilenames(title='Choose newspaper PDFs — extract SPORTS pages', filetypes=[('PDF files', '*.pdf')]))
        root.destroy()
    inputs = []
    for name in args.inputs:
        path = Path(name)
        inputs.extend(sorted(path.glob('*.pdf')) if path.is_dir() else [path])
    inputs = list(dict.fromkeys(inputs))
    if not inputs:
        return
    pages = [int(p.strip()) for p in args.pages.split(',')] if args.pages else None
    engine = None
    if not pages:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    failures = 0
    for i, path in enumerate(inputs, 1):
        print(f'\nPDF {i}/{len(inputs)}: {path.name}', flush=True)
        try:
            if extract(path, engine, args.out_dir, pages) is None:
                failures += 1
        except Exception as error:
            failures += 1
            print(f'ERROR: {path}: {error}', flush=True)
    print(f'\nFinished: {len(inputs)-failures} saved; {failures} need review.', flush=True)
    if interactive:
        input('Press Enter to close...')


if __name__ == '__main__':
    main()
