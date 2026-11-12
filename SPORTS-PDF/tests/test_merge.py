import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import pymupdf as pdf
from PIL import Image

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from merge_pdfs_by_date import collect, merge


class MergeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, day, count=1, image=None):
        path = self.root / f'paper-{day}.pdf'
        with pdf.open() as doc:
            for i in range(count):
                page = doc.new_page()
                if image:
                    page.insert_image(page.rect, stream=image)
                page.insert_text((35, 40), f'{day} page {i+1}')
            doc.save(path)
        return path

    def test_order_bookmarks_and_missing_dates(self):
        self.source('2026-10-03')
        self.source('2026-10-01', 2)
        with contextlib.redirect_stdout(io.StringIO()):
            output = merge(self.root)
        with pdf.open(output) as doc:
            self.assertEqual(len(doc), 3)
            self.assertIn('2026-10-01', doc[0].get_text())
            self.assertIn('2026-10-03', doc[2].get_text())
            self.assertEqual([r[2] for r in doc.get_toc()], [1, 3])
        report = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(report['missing_dates_between_first_and_last'], ['2026-10-02'])

    def test_duplicates_rejected_and_outputs_preserved(self):
        source = self.source('2026-10-01')
        with contextlib.redirect_stdout(io.StringIO()):
            first = merge(self.root)
            second = merge(self.root)
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        (self.root / 'duplicate-2026-10-01.pdf').write_bytes(source.read_bytes())
        with self.assertRaises(ValueError):
            collect(self.root)

    def test_compact_keeps_inputs_and_pages(self):
        image = Image.effect_noise((1600, 2200), 40).convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=99)
        source = self.source('2026-10-01', image=buffer.getvalue())
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            original = merge(self.root)
            small = merge(self.root, compact=True)
        self.assertLess(small.stat().st_size, original.stat().st_size)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        with pdf.open(original) as a, pdf.open(small) as b:
            self.assertEqual(len(a), len(b))
            self.assertEqual(a.get_toc(), b.get_toc())
            self.assertIn('2026-10-01', b[0].get_text())
            self.assertLess(min(b[0].get_pixmap().samples), 200)

    def test_signin_startup_respects_manual_stop(self):
        script = self.root / 'watch_sports.py'
        script.write_bytes((BASE / 'watch_sports.py').read_bytes())
        (self.root / 'STOP_WATCHER.txt').touch()
        result = subprocess.run([sys.executable, str(script), '--auto-start'],
                                env={**os.environ, 'PYTHONPATH': str(BASE)},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'watch_status.json').exists())


if __name__ == '__main__':
    unittest.main()
