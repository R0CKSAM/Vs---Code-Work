"""Header compatibility checks using synthetic in-memory files only."""
import csv
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import HEADERS, LEGACY_HEADERS, InvalidData, parse_upload, export_revenue


class HeaderTest(unittest.TestCase):
    def csv_upload(self, headers, total='3.25'):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerow(['2026-09-01', 'Example', 100, 40, '1.25', '2', total])
        return stream.getvalue().encode()

    def test_csv_formats_have_identical_meaning(self):
        expected = parse_upload(self.csv_upload(HEADERS), '.csv')
        self.assertEqual(parse_upload(self.csv_upload(LEGACY_HEADERS), '.csv'), expected)
        self.assertEqual(expected[0]['total'], 300)

    def test_excel_legacy_headers(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(LEGACY_HEADERS)
        book.active.append(['2026-09-01', 'Example', 100, 40, 1.25, 2, 3.25])
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        self.assertEqual(parse_upload(stream.getvalue(), '.xlsx')[0]['ad'], 100)

    def test_whole_rupee_rounding(self):
        for ad, other, total, expected in [('4.91','3921','3926',500),
                                            ('4.50','0','5',500),
                                            ('4.49','0','4',400),
                                            ('4.0000000001','0','4',400)]:
            content = ','.join(HEADERS) + f'\n2026-09-01,Example,1,1,{ad},{other},{total}\n'
            with self.subTest(ad=ad):
                row = parse_upload(content.encode(), '.csv')[0]
                self.assertEqual(row['ad'], expected)
                self.assertEqual(row['ad'] + row['other'], row['total'])

    def test_invalid_values_and_real_mismatch_rejected(self):
        for views, ad, other, total in [('1.5','4','0','4'), ('1','-0.1','0','0'),
                                      ('1','NaN','0','0'), ('1','Infinity','0','0'),
                                      ('1','4.91','3921','3927')]:
            content = ','.join(HEADERS) + f'\n2026-09-01,Example,{views},1,{ad},{other},{total}\n'
            with self.subTest(values=(views,ad,other,total)), self.assertRaises(InvalidData):
                parse_upload(content.encode(), '.csv')

    def test_export_integer_and_legacy_precision(self):
        self.assertEqual(export_revenue(392600), '3926')
        self.assertEqual(export_revenue(491), '4.91')

    def test_total_is_sum_of_rounded_components(self):
        for ad, other, total, expected in [('95.4','194.2','289.6',28900),
                                            ('44.5','172.5','217',21800)]:
            content = ','.join(HEADERS) + f'\n2026-09-01,Example,1,1,{ad},{other},{total}\n'
            with self.subTest(ad=ad):
                row = parse_upload(content.encode(), '.csv')[0]
                self.assertEqual(row['total'], expected)
                self.assertEqual(row['ad'] + row['other'], row['total'])

    def test_one_rupee_error_not_automatically_accepted(self):
        for ad, other, total in [('4.6','1699','1705'), ('16.2','1332','1349.1')]:
            content = ','.join(HEADERS) + f'\n2026-09-01,Example,1,1,{ad},{other},{total}\n'
            with self.subTest(ad=ad), self.assertRaises(InvalidData):
                parse_upload(content.encode(), '.csv')

    def test_warning_mode_preserves_excel_row_after_blank_rows(self):
        content = ','.join(HEADERS) + '\n\n2026-09-01,Example,1,1,4.6,1699,1705\n'
        row = parse_upload(content.encode(), '.csv', allow_total_warnings=True)[0]
        self.assertEqual(row['warning']['source_row'], 3)
        self.assertEqual(row['source_row'], 3)
        self.assertEqual(row['warning']['rounded_supplied_total'], 170500)

    def test_normalized_names_detect_duplicate_channel_day(self):
        content = ','.join(HEADERS) + '\n2026-09-01,Epic Music,1,1,1,0,1\n2026-09-01, EPIC   music ,1,1,1,0,1\n'
        with self.assertRaisesRegex(InvalidData, 'duplicate date/channel'):
            parse_upload(content.encode(), '.csv')
        rows = parse_upload(content.encode(), '.csv', allow_total_warnings=True)
        self.assertIn('Excel row 2', rows[1]['blocking_error'])

    def test_warning_mode_still_rejects_invalid_data(self):
        for row in ['bad-date,Example,1,1,4.6,1699,1705',
                    '2026-09-01,Example,1,1,invalid,1699,1705',
                    '2026-09-01,Example,-1,1,4.6,1699,1705']:
            with self.subTest(row=row), self.assertRaises(InvalidData):
                parse_upload((','.join(HEADERS)+'\n'+row).encode(), '.csv', allow_total_warnings=True)

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
