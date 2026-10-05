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
from app import HEADERS, AUDIT_ACTION_CATEGORIES, audit_digest, backup_database, create_app, verify_audit_chain


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

    def test_audit_categories_cover_old_events_and_paginate(self):
        actions=['user_signed_out']*105+['password_changed','upload_submitted','upload_published',
                 'upload_archived','upload_deleted','user_saved','channel_created','future_action']
        with closing(sqlite3.connect(self.db_file)) as db, db:
            last_id,previous=db.execute('SELECT id,entry_hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
            for index,action in enumerate(actions,last_id+1):
                event=dict(id=index,created='2026-10-05T08:00:00+00:00',user_id=1,actor='admin',
                           action=action,detail='Synthetic activity',prev_hash=previous)
                event['entry_hash']=audit_digest(event)
                db.execute('INSERT INTO audit(id,created,user_id,actor,action,detail,prev_hash,entry_hash) VALUES (:id,:created,:user_id,:actor,:action,:detail,:prev_hash,:entry_hash)',event)
                previous=event['entry_hash']
        data=self.client.get('/api/admin/audit?category=access').json
        self.assertTrue(data['valid'])
        self.assertEqual(data['total'],106)
        self.assertEqual(data['pages'],3)
        self.assertEqual(len(data['events']),50)
        self.assertTrue(all(event['category']=='access' for event in data['events']))
        counts={category['id']:category['count'] for category in data['categories']}
        self.assertEqual(counts['all'],114)
        self.assertEqual(counts['other'],1)
        older=self.client.get('/api/admin/audit?category=access&page=3').json
        self.assertEqual(len(older['events']),6)
        self.assertEqual(older['events'][-1]['action'],'user_signed_in')
        self.assertTrue(set(event['id'] for event in data['events']).isdisjoint(event['id'] for event in older['events']))
        self.assertEqual(self.client.get('/api/admin/audit?category=access&page=999').json['page'],3)
        other=self.client.get('/api/admin/audit?category=other').json
        self.assertEqual(other['events'][0]['action'],'future_action')
        exported=self.client.get('/api/admin/audit/export').json
        self.assertEqual(len(exported['events']),114)
        self.assertTrue(exported['valid'])

    def test_audit_category_validation_and_access(self):
        for query in ['category=unknown','page=0','page=-1','page=abc']:
            self.assertEqual(self.client.get('/api/admin/audit?'+query).status_code,400)
        empty=self.client.get('/api/admin/audit?category=delete').json
        self.assertEqual(empty['events'],[])
        self.assertEqual(empty['pages'],1)
        self.uploader_login()
        self.assertEqual(self.client.get('/api/admin/audit?category=access').status_code,403)
        self.assertEqual(self.client.get('/api/admin/audit/export').status_code,403)

    def test_admin_password_reset_has_password_activity(self):
        response=self.client.post('/api/admin/users',headers=self.headers,json={
            'id':2,'username':'uploader','role':'uploader','password':'new-synthetic-password','channels':[]})
        self.assertEqual(response.status_code,200,response.json)
        data=self.client.get('/api/admin/audit?category=passwords').json
        self.assertEqual(data['total'],1)
        self.assertEqual(data['events'][0]['action'],'password_reset_by_admin')
        self.assertNotIn('new-synthetic-password',data['events'][0]['detail'])
        self.assertTrue(data['valid'])
        self.assertEqual(AUDIT_ACTION_CATEGORIES['password_reset_completed'],'passwords')
        self.assertEqual(AUDIT_ACTION_CATEGORIES['super_admin_reset'],'passwords')

    def action(self, uid, action, body=None):
        response = self.client.post(f'/api/uploads/{uid}/{action}', headers=self.headers, json=body or {})
        self.assertEqual(response.status_code, 200, response.json)

    def test_owner_recovery_revokes_old_reset_links_and_sessions(self):
        from deploy import reset_super_admin
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.executemany('INSERT INTO email_tokens(token,user_id,expires) VALUES (?,?,?)',
                           [('owner-test-token',1,9999999999),('other-test-token',2,9999999999)])
        database=self.app.extensions['database']
        # The legacy SQLite test fixture has no SQLAlchemy migration engine.
        with patch.object(database,'check_schema'):
            reset_super_admin(database,'admin','synthetic-recovery-password')
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=1').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM email_tokens WHERE user_id=1').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM email_tokens WHERE user_id=2').fetchone()[0],1)
        with closing(self.app.extensions['database'].connect()) as db:
            self.assertTrue(verify_audit_chain(db)[0])

    def test_large_upload_and_export_use_database_only(self):
        uid = self.preview(padding=(' ' * 100 + '\n') * 6000)
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())
        self.action(uid, 'commit')
        response = self.client.get(f'/api/uploads/{uid}/file')
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(rows, [HEADERS, ['2026-09-01','Example','100','20','1','0','1']])
        with closing(sqlite3.connect(self.db_file)) as db:
            name, data = db.execute('SELECT filename,rows_json FROM uploads WHERE id=?', (uid,)).fetchone()
            self.assertEqual(name, 'example.csv')
            self.assertEqual(json.loads(data)[0]['ad'], 100)
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())

    def test_channel_rename_preserves_pending_upload_and_old_name(self):
        uid=self.preview()
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO assignments VALUES (2,1)')
        response=self.client.post('/api/admin/channels/1',headers=self.headers,data={'name':'  Example   Renamed '})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['channel']['name'],'Example Renamed')
        self.assertEqual(response.json['channel']['logo_name'],'Example')
        prepared=self.client.get(f'/api/uploads/{uid}/preview')
        self.assertEqual(prepared.status_code,200,prepared.json)
        self.assertEqual(prepared.json['rows'][0]['channel'],'Example Renamed')
        self.action(uid,'commit')
        self.assertEqual(self.client.get('/api/report').json['rows'][0]['channel'],'Example Renamed')
        self.assertEqual(self.client.get('/api/report').json['totals']['views'],100)
        old_name=self.preview('5')
        self.assertEqual(self.client.get(f'/api/uploads/{old_name}/preview').json['rows'][0]['channel_id'],1)
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT channel_id FROM assignments WHERE user_id=2').fetchone()[0],1)
        audit=self.client.get('/api/admin/audit?category=channels').json
        self.assertTrue(audit['valid'])
        self.assertTrue(any(event['action']=='channel_updated' for event in audit['events']))

    def test_channel_rename_rejects_name_and_alias_collisions(self):
        response=self.client.post('/api/admin/channels/1',headers=self.headers,data={'name':'Renamed'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/api/admin/channels',headers=self.headers,json={'name':'example'}).status_code,400)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (2,'Second')")
        for name in ['Example',' RENAMED ','']:
            self.assertEqual(self.client.post('/api/admin/channels/2',headers=self.headers,data={'name':name}).status_code,400)
        self.assertEqual(self.client.post('/api/admin/channels/1',headers=self.headers,data={'name':'Example'}).status_code,200)

    def test_channel_logos_are_normalized_replaced_and_reset_in_database(self):
        from PIL import Image
        def picture(color):
            output=io.BytesIO();Image.new('RGB',(800,400),color).save(output,format='JPEG');output.seek(0);return output
        response=self.client.post('/api/admin/channels/1',headers=self.headers,
                                  data={'name':'Example','logo':(picture('red'),'logo.jpg')})
        self.assertEqual(response.status_code,200,response.json)
        url=response.json['channel']['logo_url']
        image_response=self.client.get(url)
        self.assertEqual(image_response.mimetype,'image/png')
        with Image.open(io.BytesIO(image_response.data)) as image:
            self.assertEqual(image.size,(512,256))
        response=self.client.post('/api/admin/channels/1',headers=self.headers,
                                  data={'name':'Example','logo':(picture('blue'),'replacement.jpg')})
        self.assertEqual(response.status_code,200,response.json)
        self.assertNotEqual(url,response.json['channel']['logo_url'])
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())
        response=self.client.post('/api/admin/channels/1',headers=self.headers,data={'name':'Example','reset_logo':'true'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('logo_url',response.json['channel'])
        self.assertEqual(self.client.get(url).status_code,404)

    def test_channel_editor_requires_admin_and_assigned_logo_access(self):
        other=self.app.test_client()
        other.post('/api/login',json={'username':'uploader','password':'synthetic-password'})
        headers={'X-CSRF-Token':other.get('/api/me').json['csrf']}
        self.assertEqual(other.post('/api/admin/channels/1',headers=headers,data={'name':'Changed'}).status_code,403)
        self.assertEqual(other.get('/api/channels/1/logo').status_code,404)
        self.assertEqual(self.client.post('/api/admin/channels/1',data={'name':'Changed'}).status_code,403)

    def test_invalid_logo_does_not_partially_rename_channel(self):
        response=self.client.post('/api/admin/channels/1',headers=self.headers,
                                  data={'name':'Not saved','logo':(io.BytesIO(b'not an image'),'bad.png')})
        self.assertEqual(response.status_code,400,response.json)
        self.assertEqual(self.client.get('/api/me').json['channels'][0]['name'],'Example')

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
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 100)
        self.assertEqual(self.client.get(f'/api/uploads/{second}/file').status_code, 404)
        with closing(self.app.extensions['database'].connect()) as db:
            self.assertTrue(verify_audit_chain(db)[0])

    def test_download_requires_upload_ownership(self):
        uid = self.preview()
        other = self.app.test_client()
        other.post('/api/login', json={'username':'uploader', 'password':'synthetic-password'})
        self.assertEqual(other.get(f'/api/uploads/{uid}/file').status_code, 404)

    def upload_channel_names(self, names, actions=None, same_day=False):
        content = io.StringIO()
        writer = csv.writer(content)
        writer.writerow(HEADERS)
        for index, name in enumerate(names, 1):
            writer.writerow([f'2026-09-{1 if same_day else index:02}',name,1,1,1,0,1])
        return self.client.post('/api/uploads/preview', headers=self.headers,
                                data={'file':(io.BytesIO(content.getvalue().encode()),'channels.csv'),
                                      'channel_actions':json.dumps(actions or [])})

    def test_uploader_can_explicitly_create_and_self_assign_new_channel(self):
        self.uploader_login()
        response = self.upload_channel_names(['New file channel'], [
            {'source':'New file channel','action':'create','name':'  New   Channel '}])
        self.assertEqual(response.status_code, 200, response.json)
        row = response.json['rows'][0]
        self.assertEqual(row['channel'], 'New Channel')
        self.assertEqual(row['source_channel'], 'New file channel')
        self.assertEqual(response.json['channel_resolutions'][0]['action'], 'create')
        self.assertEqual(self.client.get('/api/report').json['rows'], [])
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT user_id FROM assignments WHERE channel_id=?', (row['channel_id'],)).fetchall(), [(2,)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='channel_created_from_upload'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='upload_channels_resolved'").fetchone()[0], 1)
        self.action(response.json['id'], 'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 100)

    def test_failed_resolution_rolls_back_created_channels_assignments_and_audit(self):
        self.uploader_login()
        response = self.upload_channel_names(['First new channel','Unresolved channel'], [
            {'source':'First new channel','action':'create'}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['channel_options'], [])
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM channels').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assignments').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM uploads').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='channel_created_from_upload'").fetchone()[0], 0)

    def test_create_cannot_claim_existing_unassigned_channel(self):
        self.uploader_login()
        for source, name in [('EXAMPLE','Something New'), ('Missing name','example')]:
            response = self.upload_channel_names([source], [{'source':source,'action':'create','name':name}])
            self.assertEqual(response.status_code, 400)
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assignments').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM channels').fetchone()[0], 1)

    def test_uploader_maps_only_to_permitted_channel(self):
        self.uploader_login()
        response = self.upload_channel_names(['A typo'], [{'source':'A typo','action':'map','channel_id':1}])
        self.assertEqual(response.status_code, 400)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO assignments VALUES (2,1)')
        response = self.upload_channel_names(['A typo'], [{'source':'A typo','action':'map','channel_id':1}])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['rows'][0]['channel'], 'Example')
        self.assertEqual(response.json['rows'][0]['source_channel'], 'A typo')
        self.action(response.json['id'], 'commit')

    def test_mapping_distinct_entries_prepares_daily_total(self):
        response = self.upload_channel_names(['First spelling','Second spelling'], [
            {'source':'First spelling','action':'map','channel_id':1},
            {'source':'Second spelling','action':'map','channel_id':1}], same_day=True)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(response.json['rows']),1)
        self.assertEqual(response.json['rows'][0]['total'],200)
        self.assertNotIn('blocking_error',response.json['rows'][0])
        commit = self.client.post('/api/uploads/'+response.json['id']+'/commit', headers=self.headers,
                                 json={'accept_total_mismatches':True,'replace':True})
        self.assertEqual(commit.status_code, 200)

    def test_mapped_preview_still_checks_current_assignment(self):
        self.uploader_login()
        response = self.upload_channel_names(['New channel'], [{'source':'New channel','action':'create'}])
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('DELETE FROM assignments WHERE user_id=2')
        commit = self.client.post('/api/uploads/'+response.json['id']+'/commit', headers=self.headers,json={})
        self.assertEqual(commit.status_code, 400)
        self.assertEqual(commit.json['channel_issues'][0]['status'], 'unassigned')

    def test_viewer_cannot_create_channels_through_upload(self):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("UPDATE users SET role='viewer' WHERE id=2")
        self.uploader_login()
        response = self.upload_channel_names(['New channel'], [{'source':'New channel','action':'create'}])
        self.assertEqual(response.status_code, 403)

    def test_resolution_source_and_action_validation(self):
        for actions in [[{'source':'Not in file','action':'create'}],
                        [{'source':'Unknown','action':'map','channel_id':True}],
                        [{'source':'Unknown','action':'create','name':' '}],
                        [{'source':'Unknown','action':'assign'}]]:
            response = self.upload_channel_names(['Unknown'], actions)
            self.assertEqual(response.status_code, 400)

    def uploader_login(self):
        response = self.client.post('/api/login', json={'username':'uploader','password':'synthetic-password'})
        self.assertEqual(response.status_code, 200)
        self.headers = {'X-CSRF-Token':self.client.get('/api/me').json['csrf']}

    def test_new_channel_can_be_reused_before_creation_in_file_order(self):
        self.uploader_login()
        response=self.upload_channel_names(['Campaign July','Campaign August','Main feed'],[
            {'source':'Campaign July','action':'map_new','target_source':' main   FEED '},
            {'source':'Campaign August','action':'map_new','target_source':'Main feed'},
            {'source':'Main feed','action':'create','name':'Government Campaigns'}])
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(len({row['channel_id'] for row in response.json['rows']}),1)
        self.assertEqual({row['channel'] for row in response.json['rows']},{'Government Campaigns'})
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM channels').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assignments WHERE user_id=2').fetchone()[0],1)
        self.action(response.json['id'],'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['total'],300)

    def test_new_channel_reuse_sums_distinct_sources_automatically(self):
        response=self.upload_channel_names(['A','B'],[
            {'source':'A','action':'create'}, {'source':'B','action':'map_new','target_source':'A'}],same_day=True)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['rows'][0]['combined_entries'],2)
        self.assertEqual(response.json['rows'][0]['total'],200)
        blocked=self.client.post('/api/uploads/'+response.json['id']+'/commit',headers=self.headers,json={'accept_total_mismatches':True})
        self.assertEqual(blocked.status_code,200)

    def test_new_channel_references_must_target_a_creation(self):
        self.uploader_login()
        for target in ['Missing','Example',{},None]:
            response=self.upload_channel_names(['A','B'],[
                {'source':'A','action':'create'}, {'source':'B','action':'map_new','target_source':target}])
            self.assertEqual(response.status_code,400,response.json)
        response=self.upload_channel_names(['A','B'],[
            {'source':'A','action':'map_new','target_source':'B'},
            {'source':'B','action':'map_new','target_source':'A'}])
        self.assertEqual(response.status_code,400)
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM channels').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assignments').fetchone()[0],0)

    def test_channel_matching_normalizes_case_spacing_and_unicode(self):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (2,'Epic Music')")
            db.execute('INSERT INTO assignments VALUES (2,2)')
        self.uploader_login()
        response = self.upload_channel_names(['  EPIC   music ', 'epic\tMusic', '\uff25\uff30\uff29\uff23\u00a0Music'])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual({row['channel_id'] for row in response.json['rows']}, {2})
        self.assertEqual({row['channel'] for row in response.json['rows']}, {'Epic Music'})
        self.action(response.json['id'], 'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 300)

    def test_all_channel_issues_grouped_with_excel_rows(self):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (2,'Archived Channel')")
            db.execute('INSERT INTO archived_channels VALUES (2)')
        self.uploader_login()
        response = self.upload_channel_names(['Unknown Name',' UNKNOWN  name ','example','Archived Channel'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['code'], 'upload_channel_issues')
        issues = response.json['channel_issues']
        self.assertEqual([issue['status'] for issue in issues], ['unknown','unassigned','archived'])
        self.assertEqual(issues[0]['rows'], [2,3])
        self.assertEqual(issues[1]['rows'], [4])
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM uploads').fetchone()[0], 0)
        self.assertEqual(self.client.post('/api/admin/channels', headers=self.headers,
                                         json={'name':'Unknown Name'}).status_code, 403)

    def test_channel_normalization_does_not_guess_punctuation(self):
        response = self.upload_channel_names(['Example-TV'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['channel_issues'][0]['status'], 'unknown')

    def test_normalized_channel_collisions_are_not_silently_resolved(self):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute("INSERT INTO channels VALUES (2,'Epic Music')")
            db.execute("INSERT INTO channels VALUES (3,'Epic  Music')")
        response = self.upload_channel_names(['EPIC MUSIC'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['channel_issues'][0]['status'], 'ambiguous')

    def test_channel_creation_normalizes_and_rejects_existing_variants(self):
        response = self.client.post('/api/admin/channels', headers=self.headers, json={'name':'  Epic   Music '})
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/api/admin/channels', headers=self.headers, json={'name':'EPIC\u00a0 music'})
        self.assertEqual(response.status_code, 400)
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute("SELECT name FROM channels WHERE id<>1").fetchall(), [('Epic Music',)])

    def test_channel_assignment_is_rechecked_before_publish(self):
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO assignments VALUES (2,1)')
        self.uploader_login()
        response = self.upload_channel_names(['EXAMPLE'])
        self.assertEqual(response.status_code, 200)
        uid = response.json['id']
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('DELETE FROM assignments WHERE user_id=2')
        response = self.client.post(f'/api/uploads/{uid}/commit', headers=self.headers, json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['channel_issues'][0]['status'], 'unassigned')
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)

    def warning_preview(self):
        content = (','.join(HEADERS) + '\n2026-09-01,Example,100,20,4.6,1699,1705\n'
                   '2026-09-02,Example,100,20,16.2,1332,1349.1\n').encode()
        response = self.client.post('/api/uploads/preview', headers=self.headers,
                                    data={'file':(io.BytesIO(content), 'totals.csv')})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_mismatch_preview_requires_explicit_acceptance(self):
        preview = self.warning_preview()
        uid = preview['id']
        self.assertEqual(preview['warning_count'], 2)
        self.assertEqual(preview['rows'][0]['warning']['source_row'], 2)
        self.assertEqual(preview['rows'][0]['warning']['supplied_total'], '1705')
        self.assertEqual(preview['rows'][0]['total'], 170400)
        self.assertEqual(self.client.get('/api/report').json['rows'], [])
        for acceptance in (None, False, 'true', 1):
            response = self.client.post(f'/api/uploads/{uid}/commit', headers=self.headers,
                                        json={'accept_total_mismatches':acceptance})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/report').json['rows'], [])
        self.action(uid, 'commit', {'accept_total_mismatches':True})
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 305200)
        with closing(self.app.extensions['database'].connect()) as db:
            event = db.execute("SELECT detail FROM audit WHERE action='upload_totals_accepted'").fetchone()
            self.assertEqual(len(json.loads(event['detail'])['warnings']), 2)
            self.assertTrue(verify_audit_chain(db)[0])
        self.assertFalse(self.app.config['UPLOAD_DIR'].exists())

    def test_saved_preview_and_unarchive_cannot_skip_acceptance(self):
        preview = self.warning_preview()
        uid = preview['id']
        self.action(uid, 'reject')
        restored = self.client.get(f'/api/uploads/{uid}/preview')
        self.assertEqual(restored.json['rows'], preview['rows'])
        self.assertEqual(restored.json['state'], 'rejected')
        self.assertEqual(self.client.get('/api/uploads').json['rows'][0]['warning_count'], 2)
        for action, body in [('unarchive', {}), ('archive', {'archived':False})]:
            response = self.client.post(f'/api/uploads/{uid}/{action}', headers=self.headers, json=body)
            self.assertEqual(response.status_code, 400)
        other = self.app.test_client()
        other.post('/api/login', json={'username':'uploader', 'password':'synthetic-password'})
        self.assertEqual(other.get(f'/api/uploads/{uid}/preview').status_code, 404)
        self.action(uid, 'unarchive', {'accept_total_mismatches':True})
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 305200)

    def test_warning_acceptance_does_not_override_replacement_check(self):
        first = self.preview()
        self.action(first, 'commit')
        preview = self.warning_preview()
        self.assertEqual(preview['duplicates'], 1)
        response = self.client.post('/api/uploads/' + preview['id'] + '/commit', headers=self.headers,
                                    json={'accept_total_mismatches':True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 100)
        self.action(preview['id'], 'commit', {'accept_total_mismatches':True, 'replace':True})

    def test_warning_acceptance_does_not_override_stale_preview(self):
        preview = self.warning_preview()
        other = self.preview('20')
        self.action(other, 'commit')
        response = self.client.post('/api/uploads/' + preview['id'] + '/commit', headers=self.headers,
                                    json={'accept_total_mismatches':True, 'replace':True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/report').json['totals']['total'], 2000)

    def test_different_values_are_included_without_extra_confirmation(self):
        content = (','.join(HEADERS) + '\n2026-09-01,Example,1,1,1,0,1\n'
                   '2026-09-01,Example,2,2,2,0,2\n').encode()
        preview = self.client.post('/api/uploads/preview', headers=self.headers,
                                  data={'file':(io.BytesIO(content), 'duplicates.csv')})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.json['rows']),1)
        self.assertEqual(preview.json['rows'][0]['views'],3)
        self.assertEqual(preview.json['rows'][0]['total'],300)
        self.assertEqual(preview.json['rows'][0]['source_entries'][1]['source_row'],3)
        uid = preview.json['id']
        for action in ('commit', 'unarchive'):
            response = self.client.post(f'/api/uploads/{uid}/{action}', headers=self.headers,
                                       json={'replace':True, 'accept_total_mismatches':True})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/report').json['totals']['total'],300)

    def repeated_preview(self, records):
        content=(','.join(HEADERS)+'\n'+'\n'.join(records)+'\n').encode()
        response=self.client.post('/api/uploads/preview',headers=self.headers,
                                  data={'file':(io.BytesIO(content),'activities.csv')})
        self.assertEqual(response.status_code,200,response.json)
        return response.json

    def test_separate_entries_combine_and_survive_full_lifecycle(self):
        data=self.repeated_preview(['2026-07-19,Example,0,9697,0,0,0','2026-07-19,Example,0,10708,0,0,0'])
        self.assertEqual(len(data['rows']),1)
        self.assertFalse(any(row.get('blocking_error') for row in data['rows']))
        uid=data['id']
        response=self.client.post(f'/api/uploads/{uid}/consolidate',headers=self.headers,json={'combine_entries':True})
        self.assertEqual(response.status_code,200,response.json)
        merged=response.json['rows'][0]
        self.assertEqual(merged['impressions'],20405)
        self.assertEqual(merged['combined_entries'],2)
        self.assertEqual([row['source_row'] for row in merged['source_entries']],[2,3])
        self.assertNotIn('blocking_error',merged)
        self.assertEqual(self.client.get('/api/report').json['rows'],[])
        self.assertEqual(self.client.get(f'/api/uploads/{uid}/preview').json['rows'][0]['impressions'],20405)
        self.action(uid,'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],20405)
        self.action(uid,'archive',{'archived':True})
        self.assertEqual(self.client.get('/api/report').json['rows'],[])
        self.action(uid,'unarchive')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],20405)
        self.action(uid,'reject')
        self.action(uid,'unarchive')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],20405)
        exported=list(csv.reader(io.StringIO(self.client.get(f'/api/uploads/{uid}/file').data.decode('utf-8-sig'))))
        self.assertEqual(exported[1][3],'20405')
        self.action(uid,'delete')
        self.assertEqual(self.client.get('/api/report').json['rows'],[])
        with closing(self.app.extensions['database'].connect()) as db:
            self.assertTrue(verify_audit_chain(db)[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='upload_entries_consolidated'").fetchone()[0],1)

    def test_exact_duplicates_are_skipped_while_different_values_are_summed(self):
        line='2026-07-19,Example,0,9697,0,0,0'
        data=self.repeated_preview([line,line,'2026-07-19,Example,0,10708,0,0,0'])
        self.assertEqual(data['rows'][0]['excluded_source_rows'],[3])
        endpoint=f"/api/uploads/{data['id']}/consolidate"
        for body in [{},{'combine_entries':'true'}]:
            self.assertEqual(self.client.post(endpoint,headers=self.headers,json=body).status_code,400)
        response=self.client.post(endpoint,headers=self.headers,json={'combine_entries':True,'skip_exact_duplicates':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['rows'][0]['impressions'],20405)
        self.assertEqual(response.json['rows'][0]['excluded_source_rows'],[3])
        self.assertEqual(len(response.json['rows'][0]['source_entries']),3)
        self.action(data['id'],'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],20405)

    def test_identical_copies_can_be_skipped_without_combining(self):
        line='2026-07-19,Example,2,3,4,5,9'
        data=self.repeated_preview([line,line])
        response=self.client.post(f"/api/uploads/{data['id']}/consolidate",headers=self.headers,json={'skip_exact_duplicates':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['rows'][0]['total'],900)
        self.assertEqual(response.json['rows'][0]['combined_entries'],1)

    def test_legacy_saved_preview_and_publish_prepare_totals_on_server(self):
        uid=self.preview('0')
        legacy=[dict(day='2026-08-21',channel='Example',channel_id=1,source_row=index,
                     views=views,impressions=impressions,ad=0,other=0,total=0,
                     blocking_error='Confirm these are separate activities before combining.')
                for index,views,impressions in [(2824,21991,174601),(2825,0,149961),(2826,0,122695)]]
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('UPDATE uploads SET rows_json=?,preview_json=? WHERE id=?',
                       (json.dumps(legacy),json.dumps([None]*3),uid))
        for _ in range(2):
            response=self.client.get(f'/api/uploads/{uid}/preview')
            self.assertEqual(response.status_code,200)
            row=response.json['rows'][0]
            self.assertEqual(len(response.json['rows']),1)
            self.assertEqual(row['views'],21991)
            self.assertEqual(row['impressions'],447257)
            self.assertNotIn('blocking_error',row)
            self.assertNotIn('Confirm these',response.text)
        self.action(uid,'commit')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],447257)
        with closing(sqlite3.connect(self.db_file)) as db:
            stored=json.loads(db.execute('SELECT rows_json FROM uploads WHERE id=?',(uid,)).fetchone()[0])
            self.assertEqual(len(stored),1)
            self.assertEqual(len(stored[0]['source_entries']),3)
        self.action(uid,'reject')
        self.action(uid,'unarchive')
        self.assertEqual(self.client.get('/api/report').json['totals']['impressions'],447257)

    def test_repeat_upload_is_detected_after_daily_totals_prepared(self):
        records=['2026-07-19,Example,0,9697,0,0,0','2026-07-19,Example,0,10708,0,0,0',
                 '2026-07-19,Example,0,9697,0,0,0']
        data=self.repeated_preview(records)
        response=self.client.post(f"/api/uploads/{data['id']}/consolidate",headers=self.headers,
                                  json={'combine_entries':True,'skip_exact_duplicates':True})
        self.assertEqual(response.status_code,200,response.json)
        content=(','.join(HEADERS)+'\n'+'\n'.join(records)+'\n').encode()
        response=self.client.post('/api/uploads/preview',headers=self.headers,
                                  data={'file':(io.BytesIO(content),'same-data.csv')})
        self.assertEqual(response.status_code,400)
        self.assertIn('already awaiting publication',response.json['error'])

    def test_consolidation_preserves_warning_acceptance(self):
        data=self.repeated_preview(['2026-09-01,Example,1,1,1,0,20','2026-09-01,Example,2,2,2,0,2'])
        uid=data['id']
        response=self.client.post(f'/api/uploads/{uid}/consolidate',headers=self.headers,json={'combine_entries':True})
        self.assertEqual(response.status_code,200,response.json)
        row=response.json['rows'][0]
        self.assertEqual(row['total'],300)
        self.assertEqual(row['warning']['supplied_total'],'22')
        self.assertEqual(row['warning']['source_warnings'][0]['source_row'],2)
        self.assertEqual(self.client.post(f'/api/uploads/{uid}/commit',headers=self.headers,json={}).status_code,400)
        self.action(uid,'commit',{'accept_total_mismatches':True})
        self.assertEqual(self.client.get('/api/report').json['totals']['total'],300)

    def test_consolidation_requires_ownership_and_current_assignment(self):
        data=self.repeated_preview(['2026-07-19,Example,0,1,0,0,0','2026-07-19,Example,0,2,0,0,0'])
        endpoint=f"/api/uploads/{data['id']}/consolidate"
        self.uploader_login()
        self.assertEqual(self.client.post(endpoint,headers=self.headers,json={'combine_entries':True}).status_code,400)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('UPDATE uploads SET user_id=2 WHERE id=?',(data['id'],))
        self.assertEqual(self.client.post(endpoint,headers=self.headers,json={'combine_entries':True}).status_code,400)
        with closing(sqlite3.connect(self.db_file)) as db, db:
            db.execute('INSERT INTO assignments VALUES (2,1)')
        self.assertEqual(self.client.post(endpoint,headers=self.headers,json={'combine_entries':True}).status_code,200)

    def test_combined_replacement_uses_one_revision_and_stale_guard(self):
        base=self.preview('5');self.action(base,'commit')
        lines=['2026-09-01,Example,1,1,1,0,1','2026-09-01,Example,2,2,2,0,2']
        data=self.repeated_preview(lines);uid=data['id']
        response=self.client.post(f'/api/uploads/{uid}/consolidate',headers=self.headers,json={'combine_entries':True})
        self.assertEqual(response.json['duplicates'],1)
        self.assertEqual(self.client.post(f'/api/uploads/{uid}/commit',headers=self.headers,json={}).status_code,400)
        self.action(uid,'commit',{'replace':True})
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions WHERE upload_id=?',(uid,)).fetchone()[0],1)
        self.action(uid,'delete')
        self.assertEqual(self.client.get('/api/report').json['totals']['total'],500)
        stale=self.repeated_preview(lines)
        other=self.preview('9');self.action(other,'commit',{'replace':True})
        response=self.client.post(f"/api/uploads/{stale['id']}/consolidate",headers=self.headers,json={'combine_entries':True})
        self.assertEqual(response.status_code,400)
        self.assertIn('Data changed',response.json['error'])

    def test_matching_values_from_distinct_mapped_sources_are_not_exact(self):
        data=self.upload_channel_names(['Campaign A','Campaign B'],[
            {'source':'Campaign A','action':'map','channel_id':1},
            {'source':'Campaign B','action':'map','channel_id':1}],same_day=True).json
        self.assertEqual(data['rows'][0]['combined_entries'],2)
        self.assertEqual(data['rows'][0]['excluded_source_rows'],[])
        response=self.client.post(f"/api/uploads/{data['id']}/consolidate",headers=self.headers,json={'combine_entries':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['rows'][0]['total'],200)

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
        self.assertIn('0,0,0', download.text)

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
