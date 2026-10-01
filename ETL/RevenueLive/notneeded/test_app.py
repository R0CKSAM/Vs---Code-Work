import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash
from app import HEADERS, InvalidData, backup_database, bootstrap, create_app, parse_upload, verify_audit_chain


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

    def test_insight_presets_validation_and_ownership(self):
        self.login('view')
        examples=self.client.get('/api/graph-presets').json['examples']
        self.assertEqual(len(examples),4)
        for example in examples:
            self.assertEqual(self.post('/api/graph-presets',example).status_code,200)
        saved=self.client.get('/api/graph-presets').json['rows']
        self.assertEqual(len(saved),4)
        config=dict(examples[0]['config'])
        for key,value in [('type',[]),('start',{}),('end',False),('channels',[2])]:
            self.assertEqual(self.post('/api/graph-presets',{'name':'Invalid','config':{**config,key:value}}).status_code,400)
        self.login('upload')
        self.assertEqual(self.client.get('/api/graph-presets').json['rows'],[])
        self.assertEqual(self.client.delete('/api/graph-presets/'+str(saved[0]['id']),headers={'X-CSRF-Token':self.csrf}).status_code,404)

    def test_reversed_date_ranges(self):
        self.login()
        forward='start=2026-09-19&end=2026-09-21'
        reverse='start=2026-09-21&end=2026-09-19'
        self.assertEqual(self.client.get('/api/report?'+forward).json,self.client.get('/api/report?'+reverse).json)
        self.assertEqual(self.client.get('/api/export?'+forward).data,self.client.get('/api/export?'+reverse).data)
        for start,end in [('2026-09-21','2026-09-19'),('2026-09-20','2026-09-20'),('','2026-09-20'),('2026-09-20','')]:
            config={'type':'line','group':'day','first':'views','second':'total','start':start,'end':end}
            self.assertEqual(self.post('/api/graph-presets',{'name':start+' to '+end,'config':config}).status_code,200)
        rows=self.client.get('/api/graph-presets').json['rows']
        saved=next(row['config'] for row in rows if row['name']=='2026-09-21 to 2026-09-19')
        self.assertEqual((saved['start'],saved['end']),('2026-09-19','2026-09-21'))
        self.assertEqual(self.client.get('/api/report?start=invalid&end=2026-09-20').status_code,400)

    def test_archive_restore_preserves_data_and_enforces_scope(self):
        self.login('view')
        self.assertEqual(self.post('/api/admin/channels/1/archive',{'archived':True}).status_code,403)
        self.login()
        self.assertEqual(self.post('/api/admin/channels/1/archive',{'archived':True}).status_code,200)
        self.assertEqual(len(self.client.get('/api/report').json['rows']),1)
        self.assertEqual(self.preview().status_code,400)
        self.assertEqual(len(self.client.get('/api/admin/users').json['archived']),1)
        self.login('view')
        self.assertEqual(self.client.get('/api/report').json['rows'],[])
        self.assertEqual(self.client.get('/api/report?channel=1').status_code,400)
        self.login()
        self.assertEqual(self.post('/api/admin/channels/1/archive',{'archived':False}).status_code,200)
        self.login('view')
        self.assertEqual(len(self.client.get('/api/report').json['rows']),1)

    def test_single_super_admin_and_admin_boundaries(self):
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db,db:
            db.execute('INSERT INTO super_admin VALUES (1,1)')
            db.execute("UPDATE users SET role='admin' WHERE id=2")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO super_admin VALUES (2,2)')
        self.login('upload')
        body={'id':1,'username':'admin','role':'admin','active':True,'channels':[]}
        self.assertEqual(self.post('/api/admin/users',body).status_code,400)
        body={'username':'another','password':'safe-admin-password','role':'admin','active':True,'channels':[]}
        self.assertEqual(self.post('/api/admin/users',body).status_code,403)
        body['id']=2;body['username']='upload';body['role']='viewer'
        self.assertEqual(self.post('/api/admin/users',body).status_code,400)
        self.login('admin')
        self.assertTrue(self.client.get('/api/me').json['user']['super_admin'])
        body.pop('id');body['username']='another';body['role']='admin'
        self.assertEqual(self.post('/api/admin/users',body).status_code,200)

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
        self.assertEqual(self.post(f'/api/uploads/{uid}/restore').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'][0]['total'],250)
        self.assertEqual(self.post(f"/api/uploads/{replacement['id']}/restore").status_code,200)
        rows=self.client.get('/api/report?start=2026-09-21').json['rows']
        self.assertEqual(rows,[])

    def test_unpublishing_latest_restores_previous_accepted_file(self):
        self.login()
        first=self.preview().json['id']
        self.assertEqual(self.post(f'/api/uploads/{first}/commit').status_code,200)
        second=self.preview(csv_file(revenue='2.50',total='2.50')).json['id']
        self.assertEqual(self.post(f'/api/uploads/{second}/commit',{'replace':True}).status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{second}/reject').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'][0]['total'],123)

    def test_unpublishing_replacements_out_of_order_skips_unpublished_ancestors(self):
        self.login()
        files=[]
        for amount in ('1.23','2.50','3.75'):
            uid=self.preview(csv_file(revenue=amount,total=amount)).json['id']
            self.assertEqual(self.post(f'/api/uploads/{uid}/commit',{'replace':True}).status_code,200)
            files.append(uid)
        self.assertEqual(self.post(f'/api/uploads/{files[1]}/reject').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'][0]['total'],375)
        self.assertEqual(self.post(f'/api/uploads/{files[2]}/reject').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'][0]['total'],123)
        self.assertEqual(self.post(f'/api/uploads/{files[0]}/reject').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])

    def test_admin_accepts_another_uploaders_file_and_controls_dates(self):
        self.login('upload')
        uid=self.preview().json['id']
        self.assertEqual(self.post('/api/admin/dates/2026-09-21/visibility',{'hidden':True}).status_code,403)
        self.login()
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)
        self.assertEqual(self.post('/api/admin/dates/2026-09-21/visibility',{'hidden':True}).status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])
        self.assertNotIn('2026-09-21',self.client.get('/api/report').json['available_dates'])
        self.assertNotIn('2026-09-21',self.client.get('/api/export').text)
        dates=self.client.get('/api/admin/dates').json['rows']
        self.assertTrue(next(row for row in dates if row['day']=='2026-09-21')['hidden'])
        upload=self.client.get('/api/uploads').json['rows'][0]
        self.assertEqual((upload['live_rows'],upload['visible_rows']),(1,0))
        self.login('view')
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])
        self.login()
        replacement=self.preview(csv_file(revenue='2.50',total='2.50')).json['id']
        self.assertEqual(self.post(f'/api/uploads/{replacement}/commit',{'replace':True}).status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])
        self.assertEqual(self.post('/api/admin/dates/2026-09-21/visibility',{'hidden':False}).status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],250)

    def test_audit_chain_is_append_only_and_detects_tampering(self):
        self.login()
        uid=self.preview().json['id']
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,200)
        audit=self.client.get('/api/admin/audit').json
        self.assertTrue(audit['valid'])
        self.assertIn('upload_published',[row['action'] for row in audit['events']])
        self.assertEqual(self.client.get('/api/admin/audit/export').status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{uid}/reject').status_code,200)
        source=next((self.path/'uploads').glob(f'{uid}_*'))
        with closing(sqlite3.connect(self.path/'revenuelive.db')) as db, db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE audit SET detail='changed' WHERE id=1")
            db.execute('DROP TRIGGER audit_no_update')
            db.execute("UPDATE audit SET detail='changed' WHERE id=1")
        self.assertFalse(self.client.get('/api/admin/audit').json['valid'])
        with self.assertRaises(RuntimeError):
            self.post(f'/api/uploads/{uid}/delete-file')
        self.assertTrue(source.exists())
        with self.assertRaises(RuntimeError):
            create_app(self.path)

    def test_legacy_audit_is_migrated_once_and_locked(self):
        legacy=self.path/'legacy-audit'
        legacy.mkdir()
        with closing(sqlite3.connect(legacy/'revenuelive.db')) as db, db:
            db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT)')
            db.execute("INSERT INTO users VALUES (1,'original-admin')")
            db.execute('CREATE TABLE audit(id INTEGER PRIMARY KEY,created TEXT,user_id INTEGER,action TEXT,detail TEXT)')
            db.execute("INSERT INTO audit VALUES (1,'2026-09-01T00:00:00+00:00',1,'channel_created','Alpha')")
        create_app(legacy)
        create_app(legacy)
        with closing(sqlite3.connect(legacy/'revenuelive.db')) as db:
            db.row_factory=sqlite3.Row
            self.assertEqual(db.execute('SELECT actor FROM audit').fetchone()['actor'],'original-admin')
            self.assertTrue(verify_audit_chain(db)[0])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM audit WHERE id=1")

    def test_pending_duplicate_content_and_discard(self):
        self.login('upload')
        first=self.preview().json['id']
        self.assertEqual(self.preview().status_code,400)
        self.assertIn('awaiting publication',self.preview(b'\xef\xbb\xbf'+csv_file()).json['error'])
        self.assertEqual(self.post(f'/api/uploads/{first}/reject').status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{first}/commit').status_code,400)
        self.assertEqual(self.preview().status_code,200)

    def test_upload_history_admin_controls(self):
        self.login('upload')
        first=self.preview().json['id']
        self.assertEqual(self.post(f'/api/uploads/{first}/archive',{'archived':True}).status_code,403)
        self.assertEqual(self.post(f'/api/uploads/{first}/delete-file').status_code,403)
        response=self.client.get(f'/api/uploads/{first}/file')
        self.assertEqual(response.status_code,200)
        response.close()
        self.login('admin')
        self.assertEqual(self.post(f'/api/uploads/{first}/archive',{'archived':True}).status_code,200)
        self.assertEqual(self.client.get('/api/uploads').json['rows'],[])
        self.assertEqual(self.post(f'/api/uploads/{first}/unarchive').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)
        self.assertEqual(self.post(f'/api/uploads/{first}/archive',{'archived':True}).status_code,200)
        self.assertEqual(self.client.get('/api/uploads').json['rows'],[])
        row=self.client.get('/api/uploads?show_archived=1').json['rows'][0]
        self.assertEqual((row['state'],row['archived'],row['file_deleted']),('committed',1,0))
        self.assertEqual(row['visible_rows'],0)
        self.assertEqual(self.post(f'/api/uploads/{first}/archive',{'archived':False}).status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{first}/delete').status_code,200)
        self.assertEqual(self.client.get(f'/api/uploads/{first}/file').status_code,404)
        self.assertEqual(self.post(f'/api/uploads/{first}/unarchive').status_code,400)
        self.assertEqual(self.client.get('/api/uploads?show_archived=1').json['rows'],[])
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])
        self.assertIn('upload_deleted',[r['action'] for r in self.client.get('/api/admin/audit').json['events']])

    def test_archive_hides_data_for_every_reader_and_preserves_versions(self):
        self.login()
        uid=self.preview().json['id']
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{uid}/archive',{'archived':True}).status_code,200)
        self.assertNotIn('2026-09-21',self.client.get('/api/export').text)
        self.login('view')
        data=self.client.get('/api/report?start=2026-09-21').json
        self.assertEqual(data['rows'],[])
        self.assertNotIn('2026-09-21',data['available_dates'])
        self.assertEqual(self.post(f'/api/uploads/{uid}/unarchive').status_code,403)
        self.login()
        self.assertEqual(self.post(f'/api/uploads/{uid}/unarchive').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)
        row=self.client.get('/api/uploads').json['rows'][0]
        self.assertEqual((row['changed_rows'],row['total_rows'],row['visible_rows']),(1,1,1))
        self.assertEqual((row['start'],row['end'],row['channel_count']),('2026-09-21','2026-09-21',1))

    def test_deleting_newer_file_never_reveals_archived_older_data(self):
        self.login()
        first=self.preview().json['id']
        self.post(f'/api/uploads/{first}/commit')
        second=self.preview(csv_file(revenue='2.50',total='2.50')).json['id']
        self.post(f'/api/uploads/{second}/commit',{'replace':True})
        self.post(f'/api/uploads/{first}/archive',{'archived':True})
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],250)
        self.assertEqual(self.post(f'/api/uploads/{second}/delete').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['rows'],[])
        self.assertEqual(self.post(f'/api/uploads/{first}/unarchive').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)

    def test_legacy_unpublished_file_can_be_unarchived_without_overwriting_newer_data(self):
        self.login()
        first=self.preview().json['id']
        self.post(f'/api/uploads/{first}/commit')
        self.post(f'/api/uploads/{first}/restore')
        self.assertEqual(self.post(f'/api/uploads/{first}/unarchive').status_code,200)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)
        self.post(f'/api/uploads/{first}/restore')
        second=self.preview(csv_file(revenue='2.50',total='2.50')).json['id']
        self.post(f'/api/uploads/{second}/commit')
        self.assertEqual(self.post(f'/api/uploads/{first}/unarchive').status_code,400)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],250)

    def test_delete_file_access_failure_rolls_back_data_and_audit(self):
        self.login()
        uid=self.preview().json['id']
        self.post(f'/api/uploads/{uid}/commit')
        count=self.client.get('/api/admin/audit').json['count']
        with patch.object(Path,'unlink',side_effect=PermissionError('File is locked')):
            self.assertEqual(self.post(f'/api/uploads/{uid}/delete').status_code,400)
        self.assertEqual(self.client.get('/api/report?start=2026-09-21').json['totals']['total'],123)
        self.assertEqual(self.client.get('/api/admin/audit').json['count'],count)
        self.assertTrue(next((self.path/'uploads').glob(f'{uid}_*')).exists())

    def test_unknown_api_returns_json_instead_of_html(self):
        response=self.client.get('/api/missing-endpoint')
        self.assertEqual(response.status_code,404)
        self.assertIsNotNone(response.json)
        self.assertIn('error',response.json)

    def test_existing_upload_table_migrates_without_losing_history(self):
        legacy=self.path/'legacy'
        legacy.mkdir()
        with closing(sqlite3.connect(legacy/'revenuelive.db')) as db, db:
            db.execute('CREATE TABLE uploads(id TEXT PRIMARY KEY,user_id INTEGER,filename TEXT,digest TEXT,created TEXT,state TEXT,rows_json TEXT,preview_json TEXT)')
            db.execute("INSERT INTO uploads VALUES ('old',1,'old.csv','hash','2026-09-01','restored','[]','[]')")
        create_app(legacy)
        with closing(sqlite3.connect(legacy/'revenuelive.db')) as db:
            self.assertEqual(db.execute("SELECT archived,file_deleted FROM uploads WHERE id='old'").fetchone(),(0,0))

    def test_published_file_cannot_be_deleted_and_unchanged_rows_not_rewritten(self):
        self.login()
        content=csv_file()+b'2026-09-20,Alpha,1,2,1.00,0,1.00\n'
        preview=self.preview(content).json
        self.assertEqual((preview['unchanged'],preview['duplicates']),(1,0))
        uid=preview['id']
        self.assertEqual(self.post(f'/api/uploads/{uid}/commit').status_code,200)
        row=self.client.get('/api/uploads').json['rows'][0]
        self.assertEqual((row['changed_rows'],row['live_rows']),(1,1))
        self.assertEqual(self.post(f'/api/uploads/{uid}/archive',{'archived':True}).status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{uid}/delete-file').status_code,400)
        response=self.client.get(f'/api/uploads/{uid}/file')
        self.assertEqual(response.status_code,200)
        response.close()
        self.assertEqual(self.post(f'/api/uploads/{uid}/restore').status_code,200)
        self.assertEqual(self.post(f'/api/uploads/{uid}/delete-file').status_code,200)
        rows=self.client.get('/api/report?start=2026-09-20&end=2026-09-20').json['rows']
        self.assertEqual(next(r for r in rows if r['channel']=='Alpha')['total'],100)

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

    def test_large_csv_rejected_before_all_rows_are_loaded(self):
        content=(','.join(HEADERS)+'\n'+'2026-09-21,Alpha,1,1,1,0,1\n'*20001).encode()
        with self.assertRaisesRegex(InvalidData, '20,000'):
            parse_upload(content,'.csv')

    def test_https_origin_cookie_and_configuration(self):
        with patch.dict(os.environ, {'REVENUE_HTTPS':'1','REVENUE_PUBLIC_URL':'https://revenue.example.com'}):
            secure=create_app(self.path/'secure')
            with closing(sqlite3.connect(self.path/'secure/revenuelive.db')) as db,db:
                db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')",
                           ('admin',generate_password_hash('safe-test-password')))
            client=secure.test_client()
            bad=client.post('/api/login',json={'username':'admin','password':'safe-test-password'},
                            headers={'Origin':'https://wrong.example.com'})
            self.assertEqual(bad.status_code,403)
            good=client.post('/api/login',json={'username':'admin','password':'safe-test-password'},
                             headers={'Origin':'https://revenue.example.com'})
            self.assertEqual(good.status_code,200)
            self.assertIn('Secure',good.headers['Set-Cookie'])
            self.assertIn('max-age=',good.headers['Strict-Transport-Security'])
            mail=self.path/'secure'/'mail.json'
            mail.write_text(json.dumps({'public_url':'https://other.example.com','host':'smtp.example.com','from':'sender@example.com'}))
            request_headers={'Origin':'https://revenue.example.com'}
            reset=client.post('/api/account/request',json={'email':'nobody@example.com'},headers=request_headers)
            self.assertEqual(reset.status_code,400)
            self.assertIn('must match',reset.json['error'])
            mail.write_text(json.dumps({'public_url':'https://revenue.example.com','host':'smtp.example.com',
                                        'from':'sender@example.com','password':'do-not-store-here'}))
            reset=client.post('/api/account/request',json={'email':'nobody@example.com'},headers=request_headers)
            self.assertEqual(reset.status_code,400)
            self.assertIn('SMTP password',reset.json['error'])
        with patch.dict(os.environ, {'REVENUE_HTTPS':'1','REVENUE_PUBLIC_URL':''}):
            with self.assertRaisesRegex(ValueError, 'REVENUE_PUBLIC_URL'):
                create_app(self.path/'invalid')

    def test_fresh_install_has_no_sample_channels_or_demo_flag(self):
        fresh=self.path/'fresh'
        bootstrap(fresh)
        with closing(sqlite3.connect(fresh/'revenuelive.db')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM channels').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM super_admin').fetchone()[0],1)
        client=create_app(fresh).test_client()
        password=(fresh/'initial_admin.txt').read_text(encoding='utf-8').split('Temporary password: ',1)[1].splitlines()[0]
        self.assertEqual(client.post('/api/login',json={'username':'admin','password':password}).status_code,200)
        self.assertNotIn('demo',client.get('/api/me').json)

    def test_compiled_backup_command_has_complete_marker(self):
        with tempfile.TemporaryDirectory() as backup_dir:
            target=backup_database(self.path,backup_dir)
            self.assertTrue((target/'revenuelive.db').is_file())
            self.assertTrue((target/'uploads').is_dir())
            self.assertTrue((target/'BACKUP_COMPLETE').is_file())
        with self.assertRaisesRegex(ValueError, 'outside'):
            backup_database(self.path,self.path/'uploads'/'nested-backups')

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
        from notneeded.demo_data import generate_rows
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
        self.assertEqual(self.client.get('/api/report?start=2026-08-31&end=2026-08-01').json,self.client.get('/api/report?start=2026-08-01&end=2026-08-31').json)
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

    def test_invitation_and_reset_are_single_use(self):
        from unittest.mock import patch
        import re
        (self.path/'mail.json').write_text(json.dumps({'public_url':'https://revenue.example.com','host':'smtp.example.com','from':'sender@example.com'}))
        self.login()
        with patch('account_email.smtplib.SMTP') as smtp:
            result=self.post('/api/admin/users',{'username':'guest@gmail.com','role':'viewer','invite':True,'channels':[1],'active':True})
            self.assertEqual(result.status_code,200,result.text)
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            token=re.search(r'account-token=([^\s]+)',message.get_content())[1]
        guest=self.app.test_client()
        self.assertEqual(guest.post('/api/account/complete',json={'token':token,'password':'guest-safe-password'}).status_code,200)
        self.assertEqual(guest.post('/api/account/complete',json={'token':token,'password':'guest-safe-password'}).status_code,400)
        self.assertEqual(guest.post('/api/login',json={'username':'guest@gmail.com','password':'guest-safe-password'}).status_code,200)
        self.assertEqual(len(guest.get('/api/report').json['rows']),1)
        with patch('account_email.smtplib.SMTP') as smtp:
            self.assertEqual(guest.post('/api/account/request',json={'email':'guest@gmail.com'}).status_code,200)
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            token=re.search(r'account-token=([^\s]+)',message.get_content())[1]
        outsider=self.app.test_client()
        self.assertEqual(outsider.post('/api/account/complete',json={'token':token,'password':'new-guest-password'}).status_code,200)
        self.assertEqual(guest.get('/api/me').status_code,401)
        self.assertEqual(outsider.post('/api/account/request',json={'email':'missing@gmail.com'}).status_code,429)
        events=self.client.get('/api/admin/audit').json['events']
        self.assertEqual(len([event for event in events if event['action']=='password_reset_completed' and event['actor']=='guest@gmail.com']),2)
        saved=next(event for event in events if event['action']=='user_saved')
        self.assertEqual(json.loads(saved['detail'])['channels'],[1])

    def test_invitation_requires_delivery_and_origin(self):
        self.login()
        self.assertEqual(self.post('/api/admin/users',{'username':'guest@gmail.com','role':'viewer','invite':True,'channels':[1]}).status_code,400)
        self.assertEqual(self.client.post('/api/account/request',json={'email':'guest@gmail.com'},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/account/complete',json={'token':'fake','password':'long-safe-password'}).status_code,400)


if __name__=='__main__':
    unittest.main()
