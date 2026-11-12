import io
from pathlib import Path
import sys
import tempfile
import unittest
import pymupdf as pdf
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from create_ai_ocr import add_text, FONT, WindowsOCR, normalize_text_maps


class OCRChecks(unittest.TestCase):
    def test_invisible_layer_and_unicode_extraction(self):
        rows = [{'text': 'SPORTS score 3-1', 'words': [{'x': 20, 'y': 30, 'width': 200, 'height': 20}]}]
        with pdf.open() as doc:
            page = doc.new_page(width=300, height=400)
            page.draw_rect(page.rect, color=(.2, .4, .6), fill=(.2, .4, .6))
            before = page.get_pixmap().samples
            add_text(page, rows, 1, pdf.Font(fontfile=str(FONT)), True)
            self.assertEqual(before, page.get_pixmap().samples)
            doc.subset_fonts()
            normalize_text_maps(doc)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'searchable.pdf'
                doc.save(path)
                with pdf.open(path) as saved:
                    self.assertIn('SPORTS score 3-1', saved[0].get_text())

    def test_visible_text_layer(self):
        rows = [{'text': 'SPORTS prize \u20b9500', 'words': [{'x': 20, 'y': 30, 'width': 200, 'height': 20}]}]
        with pdf.open() as doc:
            page = doc.new_page(width=300, height=400)
            add_text(page, rows, 1, pdf.Font(fontfile=str(FONT)), False)
            self.assertIn('SPORTS', page.get_text())
            self.assertIn('\u20b9500', page.get_text())
            self.assertLess(min(page.get_pixmap().samples), 100)

    def test_native_engine_and_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.png'
            image = Image.new('RGB', (900, 160), 'white')
            draw = ImageDraw.Draw(image)
            draw.text((20, 35), 'SPORTS FINAL SCORE 2026', fill='black', font=ImageFont.truetype(str(FONT), 42))
            image.save(path)
            engine = WindowsOCR()
            try:
                self.assertGreater(engine.max_dimension, 0)
                result = engine.read(path)
                text = ' '.join(line['text'] for line in result['lines'])
                self.assertIn('SPORTS', text)
                self.assertIn('2026', text)
                self.assertTrue(result['lines'][0]['words'])
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
