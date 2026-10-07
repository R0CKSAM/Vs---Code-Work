"""Reporting merges use synthetic records only."""
from contextlib import closing
import sqlite3
import unittest
import test_database_uploads


class ChannelMergeTest(unittest.TestCase):
    setUp = test_database_uploads.DatabaseUploadTest.setUp
    uploader_login = test_database_uploads.DatabaseUploadTest.uploader_login
    def seed(self, exact=False):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (2,'Example spelling')")
            db.execute("INSERT INTO records VALUES ('2026-10-01',1,10,20,100,0,100,'a')")
            db.execute("INSERT INTO records VALUES ('2026-10-01',2,?,30,0,0,0,'b')", (10 if exact else 25,))
            if exact:
                db.execute('UPDATE records SET views=10,impressions=20,ad=100,total=100 WHERE channel_id=2')
            db.execute('INSERT OR IGNORE INTO assignments VALUES (2,2)')

    def merge(self):
        preview=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=dict(source=2,target=1))
        self.assertEqual(preview.status_code,200,preview.json)
        body=dict(source=2,target=1,token=preview.json['token'],confirm_sum=True)
        return self.client.post('/api/admin/channel-merges',headers=self.headers,json=body)

    def test_merge_preserves_records_and_undo(self):
        self.seed()
        self.assertEqual(self.merge().status_code,200)
        result=self.client.get('/api/report?channel=1').json
        self.assertEqual(result['totals']['views'],35)
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(len(self.client.get('/api/me').json['channels']),1)
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],2)
        response=self.client.delete('/api/admin/channel-merges/2',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(self.client.get('/api/report').json['rows']),2)

    def test_partial_access_and_uploader_cannot_merge(self):
        self.seed()
        self.assertEqual(self.merge().status_code,200)
        self.uploader_login()
        response=self.client.get('/api/report')
        self.assertEqual(response.json['totals']['views'],25)
        self.assertEqual(response.json['rows'][0]['channel_id'],2)
        self.assertEqual(self.client.get('/api/report?channel=1').status_code,400)
        self.assertEqual(self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=dict(source=2,target=1)).status_code,403)
        self.assertEqual(self.client.delete('/api/admin/channel-merges/2',headers=self.headers).status_code,403)

    def test_exact_rows_are_blocked(self):
        self.seed(exact=True)
        self.assertEqual(self.merge().status_code,400)
        self.assertEqual(len(self.client.get('/api/me').json['channels']),2)

    def test_full_access_combines_but_permission_revocation_splits_again(self):
        self.seed()
        self.assertEqual(self.merge().status_code,200)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO assignments VALUES (2,1)')
        self.uploader_login()
        self.assertEqual([row['id'] for row in self.client.get('/api/me').json['channels']],[1])
        self.assertEqual(self.client.get('/api/report?channel=1').json['totals']['views'],35)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('DELETE FROM assignments WHERE user_id=2 AND channel_id=2')
        self.assertEqual(self.client.get('/api/report?channel=1').json['totals']['views'],10)

    def test_stale_records_rejected_and_audit_written(self):
        self.seed()
        plan=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=dict(source=2,target=1)).json
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('UPDATE records SET views=26 WHERE channel_id=2')
        result=self.client.post('/api/admin/channel-merges',headers=self.headers,json=dict(source=2,target=1,token=plan['token'],confirm_sum=True))
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.merge().status_code,200)
        actions=[row['action'] for row in self.client.get('/api/admin/audit?category=channels').json['events']]
        self.assertIn('channel_merged',actions)

    def test_archived_channel_data_stays_hidden(self):
        self.seed()
        self.assertEqual(self.merge().status_code,200)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO archived_channels VALUES (2)')
        self.assertEqual(self.client.get('/api/report').json['totals']['views'],10)

    def test_changed_preview_and_cycles_rejected(self):
        self.seed()
        response=self.client.post('/api/admin/channel-merges',headers=self.headers,json=dict(source=2,target=1,token='old',confirm_sum=True))
        self.assertEqual(response.status_code,400)

    def test_multiple_sources_and_individual_undo(self):
        self.seed()
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (3,'Another spelling')")
            db.execute("INSERT INTO records VALUES ('2026-10-01',3,40,50,10,0,10,'c')")
        body=dict(sources=[3,2,2],target=1)
        plan=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=body).json
        self.assertEqual(plan['sources'],[2,3])
        self.assertEqual(len(plan['source_channels']),2)
        response=self.client.post('/api/admin/channel-merges',headers=self.headers,json={**body,'token':plan['token'],'confirm_sum':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.client.get('/api/report?channel=1').json['totals']['views'],75)
        self.assertEqual(self.client.delete('/api/admin/channel-merges/3',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/report?channel=1').json['totals']['views'],35)

    def test_duplicate_between_sources_blocks_whole_merge(self):
        self.seed()
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (3,'Another spelling')")
            db.execute("INSERT INTO records VALUES ('2026-10-01',3,25,30,0,0,0,'c')")
        body=dict(sources=[2,3],target=1)
        plan=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=body).json
        self.assertEqual(plan['exact_match_dates'],['2026-10-01'])
        response=self.client.post('/api/admin/channel-merges',headers=self.headers,json={**body,'token':plan['token'],'confirm_sum':True})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/admin/channel-merges').json['rows'],[])

    def test_invalid_source_sets(self):
        self.seed()
        for sources in ([],[True],[1,2],[2,999],'2'):
            response=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=dict(sources=sources,target=1))
            self.assertEqual(response.status_code,400,(sources,response.json))
        self.assertEqual(self.merge().status_code,200)
        response=self.client.post('/api/admin/channel-merges/preview',headers=self.headers,json=dict(source=1,target=2))
        self.assertEqual(response.status_code,400)
