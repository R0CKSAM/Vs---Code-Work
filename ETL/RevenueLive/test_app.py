import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash
from app import HEADERS, InvalidData, create_app, parse_upload


def csv_file(channel='Alpha', revenue='1.23', total='1.23', day='2026-09-21'):
    return (','.join(HEADERS)+'\n'+f'{day},{channel},100,20,{revenue},0,{total}\n').encode()


class RevenueTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)
        self.app=create_app(self.path)
        self.app.testing=True
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            password=generate_password_hash('safe-test-password')
            db.executemany('INSERT INTO users(id,username,password,role) VALUES (?,?,?,?)',[(1,'admin',password,'admin'),(2,'upload',password,'uploader'),(3,'view',password,'viewer')])
            db.executemany('INSERT INTO channels VALUES (?,?)',[(1,'Alpha'),(2,'Beta')])
            db.executemany('INSERT INTO assignments VALUES (?,?)',[(2,1),(3,1)])
            db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',[('2026-09-20',1,1,2,100,0,100,'seed'),('2026-09-20',2,10,20,900,0,900,'seed')])
        self.client=self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def login(self,name='admin'):
        result=self.client.post('/api/login',json={'username':name,'password':'safe-test-password'})
        self.assertEqual(result.status_code,200)
        self.csrf=self.client.get('/api/me').json['csrf']

    def post(self,path,body=None):
        return self.client.post(path,json=body or {},headers={'X-CSRF-Token':self.csrf})

    def preview(self,content=None):
        return self.client.post('/api/uploads/preview',data={'file':(io.BytesIO(content or csv_file()),'sample.csv')},headers={'X-CSRF-Token':self.csrf})

    def test_scope_and_export(self):
        self.login('view')
        data=self.client.get('/api/report').json
        self.assertEqual(data['totals']['total'],100)
        self.assertEqual(len(data['rows']),1)
        self.assertNotIn('Beta',self.client.get('/api/export').text)
        self.assertEqual(self.client.get('/api/report?channel=2').status_code,400)
        self.assertEqual(self.client.get('/api/admin/users').status_code,403)
        self.assertEqual(self.preview().status_code,403)

    def test_empty_assignment(self):
        self.login('view')
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            db.execute('DELETE FROM assignments WHERE user_id=3')
        self.assertEqual(self.client.get('/api/report').json['rows'],[])

    def test_mixed_upload_rejected_atomically(self):
        self.login('upload')
        content=csv_file()+b'2026-09-21,Beta,1,1,1,0,1\n'
        self.assertEqual(self.preview(content).status_code,400)
        self.assertEqual(len(self.client.get('/api/report').json['rows']),1)

    def test_upload_duplicate_and_rollback(self):
        self.login()
        result=self.preview();self.assertEqual(result.status_code,200,result.text)
        uid=result.json['id']
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,200)
        self.assertEqual(self.preview().status_code,400)
        replacement=self.preview(csv_file(revenue='2.50',total='2.50')).json
        self.assertEqual(replacement['duplicates'],1)
        path=f"/api/uploads/{replacement['id']}/commit"
        self.assertEqual(self.post(path).status_code,400)
        self.assertEqual(self.post(path,{'replace':True}).status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{uid}/restore').status_code,400)
        self.assertEqual(self.post(f"/api/uploads/{replacement['id']}/restore").status_code,200)
        rows=self.client.get('/api/report?start=2026-09-21').json['rows']
        self.assertEqual(rows[0]['total'],123)

    def test_stale_preview(self):
        self.login()
        a=self.preview().json['id']
        b=self.preview(csv_file(revenue='2',total='2')).json['id']
        self.assertEqual(self.post(f'/api/uploads/{a}/commit').status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{b}/commit').status_code,400)

    def test_permission_rechecked_after_preview(self):
        self.login('upload')
        uid=self.preview().json['id']
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            db.execute('DELETE FROM assignments WHERE user_id=2')
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,400)

    def test_csrf_and_unauthenticated(self):
        self.assertEqual(self.client.get('/api/report').status_code,401)
        self.login()
        self.assertEqual(self.client.post('/api/admin/channels',json={'name':'Gamma'}).status_code,403)
        self.assertEqual(self.client.post('/api/logout',headers={'X-CSRF-Token':self.csrf,'Origin':'https://evil.example'}).status_code,403)

    def test_validation(self):
        for content in [csv_file(revenue='1',total='2'),csv_file(revenue='-1',total='-1'),csv_file(revenue='NaN',total='NaN'),csv_file(day='21/09/2026'),csv_file()+csv_file().split(b'\n')[1]+b'\n']:
            with self.assertRaises(InvalidData):
                parse_upload(content,'.csv')

    def test_admin_user_create_and_self_lock(self):
        self.login()
        body={'username':'new','role':'viewer','password':'new-safe-password','channels':[1],'active':True}
        self.assertEqual(self.post('/api/admin/users',body).status_code,200)
        self.assertEqual(self.post('/api/admin/users',body).status_code,400)
        self.assertEqual(self.post('/api/admin/users',{'id':1,'username':'admin','role':'viewer','active':True}).status_code,400)

    def test_sample_workbook(self):
        sample=Path(__file__).parent/'Upload File.xls'
        if not sample.exists():
            self.skipTest('Sample not packaged')
        rows=parse_upload(sample.read_bytes(),'.xls')
        self.assertEqual(len(rows),28)
        self.assertEqual(sum(r['total'] for r in rows),31389)
        self.assertEqual(sum(r['views'] for r in rows),149938)

    def test_temporary_password_blocks_data_until_changed(self):
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            db.execute('UPDATE users SET must_change=1 WHERE id=3')
        self.login('view')
        self.assertEqual(self.client.get('/api/report').status_code,403)
        self.assertEqual(self.post('/api/password',{'current':'safe-test-password','password':'changed-safe-password'}).status_code,200)
        self.assertEqual(self.client.get('/api/report').status_code,200)

    def test_disabled_user_loses_session(self):
        self.login('view')
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            db.execute('UPDATE users SET active=0 WHERE id=3')
        self.assertEqual(self.client.get('/api/report').status_code,401)

    def test_month_filter_matrix_and_export(self):
        import csv
        from demo_data import generate_rows
        from urllib.parse import urlencode
        generated=generate_rows([(1,'Alpha'),(2,'Beta')])
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db,db:
            db.execute('DELETE FROM records')
            db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',generated)
        self.login()
        ranges=[('',''),('2026-08-01','2026-08-01'),('2026-08-12','2026-08-12'),('2026-08-03','2026-08-09'),('2026-08-01','2026-08-31'),('2026-09-01','2026-09-30')]
        for ids in [[],[1],[2],[1,2],[1,1],['none']]:
            for start,end in ranges:
                with self.subTest(ids=ids,start=start,end=end):
                    params=[('channel',str(cid)) for cid in ids]+[('start',start),('end',end)]
                    query=urlencode(params)
                    expected=[r for r in generated if (not ids or r[1] in ids) and (not start or r[0]>=start) and (not end or r[0]<=end)]
                    result=self.client.get('/api/report?'+query)
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(len(result.json['rows']),len(expected))
                    self.assertEqual(result.json['totals']['total'],sum(r[6] for r in expected))
                    exported=list(csv.reader(io.StringIO(self.client.get('/api/export?'+query).text.lstrip('\ufeff'))))
                    self.assertEqual(len(exported)-1,len(expected))
        self.assertEqual(self.client.get('/api/report?start=2026-08-31&end=2026-08-01').status_code,400)
        self.login('view')
        self.assertEqual(self.client.get('/api/report?channel=1&channel=2').status_code,400)

    def test_cookie_namespace_isolates_instances(self):
        first=self.client.post('/api/login',json={'username':'admin','password':'safe-test-password'})
        other_path=self.path/'separate'
        other=create_app(other_path)
        with closing(sqlite3.connect(other_path/'revenuelive.db')) as db,db:
            db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')",('admin',generate_password_hash('safe-test-password')))
        second=other.test_client().post('/api/login',json={'username':'admin','password':'safe-test-password'})
        self.assertNotEqual(first.headers['Set-Cookie'].split('=')[0],second.headers['Set-Cookie'].split('=')[0])


if __name__=='__main__':
    unittest.main()
