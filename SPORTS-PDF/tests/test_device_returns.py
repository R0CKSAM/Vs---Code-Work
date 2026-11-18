import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze_device_returns import analyze

class DeviceReturns(unittest.TestCase):
 def test_cross_date_returns_and_ip_changes(self):
  with tempfile.TemporaryDirectory(prefix='veto-device-returns-') as temp:
   root=Path(temp);source=root/'input.parquet'
   rows=[('2026-11-01','A','IP1'),('2026-11-01','A','IP1'),('2026-11-01','A','IP2'),('2026-11-01','unknown','IP3'),('2026-11-03','A','IP1'),('2026-11-03','A','IP4'),('2026-11-03','B','IP3'),('2026-11-04','B','IP5'),('2026-11-04','','IP6')]
   pq.write_table(pa.Table.from_pylist([{'ist_date':dt,'device_id':dev,'cli_ip':ip,'raw_ts_requests':0} for dt,dev,ip in rows]),source)
   before=source.read_bytes()
   with contextlib.redirect_stdout(io.StringIO()):result=analyze(source,root/'out')
   self.assertEqual(source.read_bytes(),before)
   self.assertEqual([(d['date_ist'],d['total_device_ids'],d['returning_device_ids']) for d in result['daily']],[('2026-11-01',1,0),('2026-11-03',2,1),('2026-11-04',1,1)])
   self.assertEqual(result['quality']['valid_distinct_device_ids'],2)
   self.assertEqual(result['quality']['valid_device_ids_with_positive_ts'],0)
   self.assertEqual(result['daily_ip_relationship'][1]['returning_devices_with_new_ip'],1)
   self.assertEqual(result['daily_ip_relationship'][0]['devices_on_multiple_ips_same_day'],1)
   self.assertFalse(result['ua_available'])

if __name__=='__main__':unittest.main()
