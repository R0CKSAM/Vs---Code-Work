import gzip,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from validate_raw_grafana import parse_record,query_ids,process_chunk,aggregate,COLS

class RawChecks(unittest.TestCase):
 def row(self,**changes):
  r={'reqTimeSec':'1794787200.25','reqHost':'veto.example','cliIP':'192.0.2.1','UA':'Test','statusCode':'200','reqPath':'a/main_123.ts','queryStr':'device_id=d%20one&session_id=s1','bytes':'50','country':'IN','state':'Delhi','city':'NEWDELHI'};r.update(changes);return r
 def parse(self,**changes):
  r=self.row(**changes);return dict(zip(COLS,parse_record(r,json.dumps(r).encode())))
 def test_conditions(self):
  self.assertTrue(self.parse()['eligible_ts']);self.assertFalse(self.parse(statusCode='404')['eligible_ts']);self.assertTrue(self.parse(statusCode='206')['eligible_ts']);self.assertFalse(self.parse(reqPath='a/segment.ts')['eligible_ts']);self.assertFalse(self.parse(reqPath='a/main_12.ts?x=y')['eligible_ts']);self.assertTrue(self.parse(reqPath='a/main.m3u8')['master'])
 def test_identifiers_and_timestamp(self):
  r=self.parse();self.assertEqual(r['time_us'],1794787200250000);self.assertEqual(r['device'],'d one');self.assertEqual(r['session'],'s1');self.assertEqual(query_ids('device_id%3Dx%26session_id%3Dy'),('x','y'));self.assertEqual(self.parse(queryStr='')['device'],'');self.assertRaises(ValueError,lambda:self.parse(reqTimeSec='bad'))
 def test_resume_duplicates_and_boundaries(self):
  with tempfile.TemporaryDirectory(prefix='veto-raw-test-') as temp:
   out=Path(temp);parts=out/'parts';parts.mkdir();f=out/'sample.gz'
   rows=[self.row(reqTimeSec='1794777000'),self.row(reqTimeSec='1794863400'),self.row(reqTimeSec='1794777000')]
   with gzip.open(f,'wb') as z:
    for r in rows:z.write(json.dumps(r).encode()+b'\n')
   st=f.stat();task=(0,[(str(f),st.st_size,st.st_mtime_ns)],str(parts),'test')
   first=process_chunk(task);self.assertEqual(first['rows'],3);self.assertEqual(process_chunk(task),first)
   s=aggregate(parts,out,'2026-11-16');v=s['windows']['target_full_ist_day']['metrics'];self.assertEqual(v['raw_rows'],2);self.assertEqual(v['distinct_raw_lines'],1);self.assertAlmostEqual(v['hours_6'],2*6/3600);self.assertEqual(v['users_including_blank'],1)
 def test_bad_gzip_and_bad_rows_reported(self):
  with tempfile.TemporaryDirectory(prefix='veto-raw-test-') as temp:
   root=Path(temp);parts=root/'parts';parts.mkdir();f=root/'bad.gz';f.write_bytes(b'bad gzip');st=f.stat();r=process_chunk((0,[(str(f),st.st_size,st.st_mtime_ns)],str(parts),'bad'));self.assertEqual(r['errors'],1)
   f=root/'row.gz'
   with gzip.open(f,'wb') as z:z.write(b'not json\n')
   st=f.stat();r=process_chunk((1,[(str(f),st.st_size,st.st_mtime_ns)],str(parts),'badrow'));self.assertEqual(r['bad_rows'],1)

if __name__=='__main__':unittest.main()
