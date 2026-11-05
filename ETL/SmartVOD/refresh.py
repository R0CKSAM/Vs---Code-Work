"""Daily completed-day refresh. Never replace the live snapshot on a failed build."""
import json,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from prepare_v2 import ROOT,ETL,publish

def main():
    folder=ROOT/'data';folder.mkdir(exist_ok=True)
    state={'started':datetime.now().isoformat(),'status':'running'}
    status=folder/'refresh_status.json'
    def record():
        tmp=status.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(status)
    record()
    try:
        yesterday=(datetime.now(timezone(timedelta(hours=5,minutes=30))).date()-timedelta(days=1)).isoformat()
        meta=json.loads((folder/'manifest.json').read_text())
        first=meta['dates'][0]
        dates=set(meta['dates'])
        for p in (ETL/'output/exports').glob('vod_stream_query_events_????-??-??.csv'):
            d=p.stem[-10:]
            if first<=d<=yesterday:dates.add(d)
        # Only extract a missing completed day; reuse published VOD exports where available.
        days=[];d=datetime.fromisoformat(max(meta['dates']))+timedelta(days=1)
        while d.date().isoformat()<=yesterday:
            days.append(d.date().isoformat());d+=timedelta(days=1)
        sources=folder/'sources';sources.mkdir(exist_ok=True)
        skipped=[]
        with (folder/'refresh.log').open('a',encoding='utf-8') as log:
            for day in days:
                if day in dates:continue
                validation=folder/'validation'/day
                result=subprocess.run([sys.executable,str(ETL/'src/tools/validate_daily_delivery.py'),'--lake',str(ETL/'data/lake'),'--archive-lake',r'Z:\Veto Logs Backup\DO NOT DELETE','--date',day,'--sources','stream','--mode','structural','--output-dir',str(validation)],stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:
                    skipped.append(day);continue
                report=json.loads((validation/'daily_delivery_validation_latest.json').read_text())
                source=report['source_results'][0]
                if source['status']!='PASS' or not source['selected']['full_day']:
                    skipped.append(day);continue
                files=[Path(f['path']) for f in source['selected']['files']]
                parents={f.parent for f in files}
                if len(parents)!=1 or not all(f.exists() for f in files):
                    skipped.append(day);continue
                dest=sources/f'vod_stream_query_events_{day}.csv';tmp=dest.with_suffix('.pending.csv')
                subprocess.run([sys.executable,str(ETL/'src/tools/export_vod_query_events.py'),'--input',str(files[0].parent),'--date',day,'--out',str(tmp),'--compact','--threads','2','--memory-limit','4GB','--temp-dir',str(folder/'scratch')],stdout=log,stderr=subprocess.STDOUT,check=True)
                tmp.replace(dest);dates.add(day)
        result=publish(sorted(dates),incremental=True)
        state.update(status='complete' if not skipped else 'waiting_for_completed_lake',through=result['dates'][-1],skipped_dates=skipped,database=result['database'])
    except Exception as e:
        state.update(status='failed',error=str(e));raise
    finally:
        state['finished']=datetime.now().isoformat();record()
if __name__=='__main__':main()
