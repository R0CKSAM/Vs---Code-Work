import contextlib,io,json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
from server import build,Explorer,Handler,ThreadingHTTPServer

class ExplorerChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='veto-identity-test-');cls.root=Path(cls.temp.name);src=cls.root/'source.parquet';rows=[]
  for dt,dev,ip,event in [('2026-11-01','device_alpha_0001','198.51.100.1','One'),('2026-11-01','device_beta_0002','198.51.100.1','Two'),('2026-11-03','device_alpha_0001','198.51.100.2','Two'),('2026-11-03','device_gamma_0003','198.51.100.3','One'),('2026-11-03','','198.51.100.4','One'),('2026-11-03','unknown','198.51.100.4','One')]:
   rows.append({'ist_date':dt,'device_id':dev,'cli_ip':ip,'Event Name':event,'Match Name':event+' match','ReqHost':'example.invalid','country':'IN','state':'New%20Delhi','Device Type':'smartphone','OS Type':'Android','ISP':'Example ISP','raw_ts_requests':0 if dev else 10})
  pq.write_table(pa.Table.from_pylist(rows),src);cls.source=src;cls.cache=cls.root/'cache.duckdb'
  with contextlib.redirect_stdout(io.StringIO()):build(src,cls.cache)
  cls.e=Explorer(cls.cache)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_identity_scope_and_coverage(self):
  d=self.e.overview({});self.assertEqual(d['summary']['devices'],3);self.assertEqual(d['summary']['ips'],4);self.assertEqual(d['summary']['missing_device_rows'],2);self.assertEqual(d['daily'][1]['returning_devices'],1)
 def test_shared_ip_not_person_merge(self):
  d=self.e.explore({'kind':'ip','identifier':'198.51.100.1'});self.assertEqual(d['summary']['devices'],2);self.assertEqual(len(d['neighbors']),2)
 def test_device_moves_ip(self):
  d=self.e.explore({'kind':'device','identifier':'device_alpha_0001'});self.assertEqual(d['summary']['ips'],2);self.assertEqual(len(d['timeline']),2);self.assertEqual(d['all_file_device_profile'][0]['active_dates'],2)
 def test_unlinked_ip_keeps_unknown_identity(self):
  d=self.e.explore({'kind':'ip','identifier':'198.51.100.4'});self.assertEqual(d['summary']['devices'],0);self.assertEqual(d['neighbors'],[])
 def test_filtered_returns_use_complete_file_baseline(self):
  d=self.e.overview({'from':'2026-11-03','to':'2026-11-03','event':'Two'});self.assertEqual(d['summary']['devices'],1);self.assertEqual(d['daily'][0]['returning_devices'],1)
 def test_unknown_id_and_sql_input(self):
  for identifier in ['unknown_identifier',"x' OR 1=1 --"]:self.assertEqual(self.e.explore({'kind':'device','identifier':identifier})['summary']['source_rows'],0)
  with self.assertRaises(ValueError):self.e.explore({'kind':'device','identifier':'x','offset':-1})
  with self.assertRaises(ValueError):self.e.overview({'event':'unknown'})
 def test_cohorts_not_sessions(self):
  c=self.e.cohorts({});self.assertEqual(sum(x['devices'] for x in c['sizes']),3);self.assertEqual(len(c['coverage']),2);self.assertFalse(self.e.meta['ua_available']);self.assertFalse(self.e.meta['session_id_available'])
 def test_snapshot_reused_and_source_not_changed(self):
  original=self.source.read_bytes();mtime=self.cache.stat().st_mtime_ns;build(self.source,self.cache);self.assertEqual(self.cache.stat().st_mtime_ns,mtime);self.assertEqual(original,self.source.read_bytes())
 def test_loopback_api_and_origin_guards(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.explorer=self.e;t=threading.Thread(target=server.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{server.server_port}'
  try:
   with urllib.request.urlopen(url+'/health') as r:self.assertEqual(json.load(r)['application'],'veto-identity-explorer')
   data=json.dumps({'kind':'device','identifier':'device_alpha_0001'}).encode()
   request=urllib.request.Request(url+'/api/explore',data=data,headers={'Content-Type':'application/json','Origin':url})
   with urllib.request.urlopen(request) as r:self.assertEqual(json.load(r)['summary']['ips'],2)
   request=urllib.request.Request(url+'/api/explore',data=data,headers={'Content-Type':'application/json','Origin':'https://other.example'})
   with self.assertRaises(urllib.error.HTTPError) as r:urllib.request.urlopen(request)
   self.assertEqual(r.exception.code,403)
  finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()
