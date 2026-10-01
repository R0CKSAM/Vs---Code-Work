"""Synthetic local tests; never load deployment secrets or connect to live SQL."""
import csv
from contextlib import closing
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash
from app import HEADERS, backup_database, create_app, verify_audit_chain


class DatabaseUploadTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.loader = patch('config.load_environment')
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.app = create_app(self.root / 'data')
        self.app.testing = True
        self.db_file = self.root / 'data' / 'revenuelive.db'
        with closing(sqlite3.connect(self.db_file)) as db, db:
            password = generate_password_hash('synthetic-password')
            db.executemany('INSERT INTO users(id,username,password,role,must_change) VALUES (?,?,?,?,0)',
                           [(1, 'admin', password, 'admin'), (2, 'uploader', password, 'uploader')])
            db.execute("INSERT INTO channels VALUES (1,'Example')")
        self.client = self.app.test_client()
        self.client.post('/api/login', json={'username':'admin', 'password':'synthetic-password'})
        self.headers = {'X-CSRF-Token':self.client.get('/api/me').json['csrf']}

    def preview(self, value='1.23', padding=''):
        content = (','.join(HEADERS) + f'\n2026-09-01,Example,100,20,{value},0,{value}\n' + padding).encode()
        response = self.client.post('/api/uploads/preview', headers=self.headers,
                                    data={'file':(io.BytesIO(content), 'example.csv')})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['id']

    def action(self, uid, action, body=None):
        response = self.client.post(f'/api/uploads/{uid}/{action}', headers=self.headers, json=body or {})
        self.assertEqual(response.status_code, 200, response.json)

    def test_large_upload_and_export_use_database_only(self):
        uid = self.preview(padding=(' ' * 100 + '\n') * 6000)
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())
        self.action(uid, 'commit')
        response = self.client.get(f'/api/uploads/{uid}/file')
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(rows, [HEADERS, ['2026-09-01','Example','100','20','1.23','0.00','1.23']])
        with closing(sqlite3.connect(self.db_file)) as db:
            name, data = db.execute('SELECT filename,rows_json FROM uploads WHERE id=?', (uid,)).fetchone()
            self.assertEqual(name, 'example.csv')
            self.assertEqual(json.loads(data)[0]['ad'], 123)
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())

    def test_archive_delete_restore_without_original_files(self):
        first = self.preview()
        self.action(first, 'commit')
        second = self.preview('2.34')
        self.action(second, 'commit', {'replace':True})
        self.action(second, 'archive', {'archived':True})
        self.assertEqual(self.client.get('/api/report').json['rows'], [])
        self.assertEqual(self.client.get(f'/api/uploads/{second}/file').status_code, 200)
        self.action(second, 'unarchive')
        self.action(second, 'delete')
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 123)
        self.assertEqual(self.client.get(f'/api/uploads/{second}/file').status_code, 404)
        with closing(self.app.extensions['database'].connect()) as db:
            self.assertTrue(verify_audit_chain(db)[0])

    def test_download_requires_upload_ownership(self):
        uid = self.preview()
        other = self.app.test_client()
        other.post('/api/login', json={'username':'uploader', 'password':'synthetic-password'})
        self.assertEqual(other.get(f'/api/uploads/{uid}/file').status_code, 404)

    def test_excel_download_is_csv(self):
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.append(HEADERS)
        workbook.active.append(['2026-09-01','Example',1,2,0.10,0.20,0.30])
        content = io.BytesIO()
        workbook.save(content)
        content.seek(0)
        response = self.client.post('/api/uploads/preview', headers=self.headers,
                                    data={'file':(content, 'report.xlsx')})
        self.assertEqual(response.status_code, 200)
        download = self.client.get('/api/uploads/' + response.json['id'] + '/file')
        self.assertIn('report.csv', download.headers['Content-Disposition'])
        self.assertIn('0.10,0.20,0.30', download.text)

    def test_backup_needs_no_original_upload_directory(self):
        self.preview()
        target = backup_database(self.root / 'data', self.root / 'backups')
        self.assertTrue((target / 'BACKUP_COMPLETE').exists())
        self.assertFalse((target / 'uploads').exists())
        with closing(sqlite3.connect(target / 'revenuelive.db')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM uploads').fetchone()[0], 1)

    def test_log_rotation_bounds_disk_usage(self):
        from runtime_logging import configure_logging
        root_logger = logging.getLogger()
        old_handlers, old_level = root_logger.handlers[:], root_logger.level
        root_logger.handlers = []
        try:
            with patch.dict(os.environ, {'LOG_MAX_BYTES':'65536', 'LOG_BACKUP_COUNT':'2'}), patch.object(sys, 'excepthook'):
                configure_logging(self.root)
                for _ in range(400):
                    logging.getLogger('synthetic').info('x' * 1024)
                files = list((self.root / 'logs').glob('revenuelive.log*'))
                self.assertEqual(len(files), 3)
                self.assertTrue(all(file.stat().st_size <= 65536 for file in files))
        finally:
            for handler in root_logger.handlers:
                handler.close()
            root_logger.handlers = old_handlers
            root_logger.setLevel(old_level)


if __name__ == '__main__':
    unittest.main()
