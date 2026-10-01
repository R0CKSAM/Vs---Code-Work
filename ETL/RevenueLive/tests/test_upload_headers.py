"""Header compatibility checks using synthetic in-memory files only."""
import csv
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import HEADERS, LEGACY_HEADERS, InvalidData, parse_upload


class HeaderTest(unittest.TestCase):
    def csv_upload(self, headers, total='3.50'):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerow(['2026-09-01', 'Example', 100, 40, '1.25', '2.25', total])
        return stream.getvalue().encode()

    def test_csv_formats_have_identical_meaning(self):
        expected = parse_upload(self.csv_upload(HEADERS), '.csv')
        self.assertEqual(parse_upload(self.csv_upload(LEGACY_HEADERS), '.csv'), expected)
        self.assertEqual(expected[0]['total'], 350)

    def test_excel_legacy_headers(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(LEGACY_HEADERS)
        book.active.append(['2026-09-01', 'Example', 100, 40, 1.25, 2.25, 3.50])
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        self.assertEqual(parse_upload(stream.getvalue(), '.xlsx')[0]['ad'], 125)

    def test_case_and_whitespace(self):
        headers = ['  ' + name.upper().replace(' ', '\n') + '  ' for name in LEGACY_HEADERS]
        self.assertEqual(parse_upload(self.csv_upload(headers), '.csv')[0]['impressions'], 40)

    def test_legacy_total_must_include_sponsorship(self):
        with self.assertRaisesRegex(InvalidData, 'total revenue must equal'):
            parse_upload(self.csv_upload(LEGACY_HEADERS, '1.25'), '.csv')

    def test_ambiguous_or_reordered_headers_rejected(self):
        ambiguous = HEADERS.copy()
        ambiguous[4] = 'Revenue'
        reordered = HEADERS.copy()
        reordered[3], reordered[4] = reordered[4], reordered[3]
        for headers in (ambiguous, reordered, HEADERS[:-1], HEADERS + ['Extra']):
            with self.subTest(headers=headers), self.assertRaisesRegex(InvalidData, 'Columns must match'):
                parse_upload(self.csv_upload(headers), '.csv')


if __name__ == '__main__':
    unittest.main()
