"""Remove confirmed redundant intermediates after the November 3 ASRUN publication."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import psutil
import pyarrow.parquet as pq

ETL = Path(__file__).resolve().parents[2]
ARCHIVE = Path(r'Z:\Veto Logs Backup\DO NOT DELETE').resolve()
TEMP = ARCHIVE / 'Temp/VetoETL'
LATEST = TEMP / 'asrun_refresh/20261103_132519'
ACTIVE = TEMP / 'ITVINTERN03/daily_20261102'

def targets():
    items = []
    for run in ('20261102_172035','20261103_102423','20261103_114604','20261103_122323'):
        for name in ('scratch','dashboard','parsed','previous_dashboard'):
            items.append(TEMP / 'asrun_refresh' / run / name)
    # Preserve latest audience/parser cache and its rollback copy.
    items += [LATEST/'scratch', LATEST/'dashboard', ETL/'asrun_demo/backups',
              ETL/'asrun_demo/.publish_asrun_refresh_20261102_191017',
              TEMP/'retained_intermediates/cleanup_20261014/previous_dashboard',
              TEMP/'retained_intermediates/legacy_stream_20261011_parquet']
    for source, raw_name in (('stream','Veto Stream Backup'),('fast','Veto fast Backup')):
        for month, day in (('10','30'),('10','31'),('11','01')):
            items.append(ETL/'data/raw/Veto Logs Backup'/raw_name/month/day)
            for folder in ('stage/parquet','stage/final_clean'):
                items.append(ETL/'data'/folder/f'source={source}/year=2026/month={month}/day={day}')
    return [p for p in items if p.exists()]

def guard(path):
    resolved = path.resolve()
    roots = [TEMP, ETL/'data', ETL/'asrun_demo/backups', ETL/'asrun_demo/.publish_asrun_refresh_20261102_191017']
    assert any(resolved.is_relative_to(r.resolve()) for r in roots)
    assert resolved != TEMP and not resolved.is_relative_to(ACTIVE)
    assert not resolved.is_relative_to(TEMP/'raw')
    assert not path.is_symlink() and not path.is_junction()
    for parent in path.parents:
        if parent == TEMP or parent == ETL: break
        assert not parent.is_symlink() and not parent.is_junction()
    for process in psutil.process_iter(['pid','cmdline']):
        if process.pid == os.getpid(): continue
        command = ' '.join(process.info['cmdline'] or []).casefold()
        assert str(path).casefold() not in command and str(resolved).casefold() not in command, f'In use: {path}'
    return resolved

def inventory(path):
    count = size = 0
    pending = [path]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                assert not (getattr(info, 'st_file_attributes', 0) & 0x400), f'Nested reparse point: {entry.path}'
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                else:
                    size += info.st_size
                    count += 1
    return count, size

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    state=json.loads((ETL/'output/state/asrun_available_refresh.json').read_text())
    assert state['status']=='complete' and Path(state['work']).resolve()==LATEST
    assert json.loads((ETL/'output/validation/asrun_browser_audit.json').read_text())['passed']
    assert json.loads((ETL/'output/validation/asrun_payload_audit.json').read_text())['passed']
    for day in ('2026-10-11','2026-10-12'):
        subprocess.run([sys.executable,str(ETL/'src/tools/validate_daily_delivery.py'),
            '--lake',str(ARCHIVE),'--archive-lake',str(ETL/'data/lake'),
            '--date',day,'--sources','stream','--mode','structural',
            '--output-dir',str(ETL/'output/validation/pre_cleanup'/day)],check=True)
    for day in ('2026-10-30','2026-10-31','2026-11-01'):
        subprocess.run([sys.executable,str(ETL/'src/tools/validate_daily_delivery.py'),
            '--lake',str(ARCHIVE),'--date',day,'--sources','stream,fast','--mode','structural',
            '--output-dir',str(ETL/'output/validation/pre_cleanup'/day)],check=True)
    # A staged dashboard is redundant only after every published file matches its size.
    for p in (LATEST/'dashboard').rglob('*'):
        if p.is_file():
            published=ETL/'asrun_demo/output'/p.relative_to(LATEST/'dashboard')
            assert published.is_file() and published.stat().st_size==p.stat().st_size
    audit=ETL/'output/cleanup'/('post_publication_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    result={'status':'running','execute':args.execute,'groups':[],
            'free_before':{'D':shutil.disk_usage('D:/').free,'Z':shutil.disk_usage(ARCHIVE).free}}
    def save(): audit.write_text(json.dumps(result,indent=2),encoding='utf-8')
    save()
    try:
        for path in targets():
            resolved=guard(path)
            print('Inspecting '+str(resolved),flush=True)
            count,size=inventory(resolved)
            item={'path':str(resolved),'files':count,'bytes':size,'status':'planned'}
            result['groups'].append(item);save()
            print(f'{count:,} files; {size/1024**3:.2f} GiB',flush=True)
            if args.execute:
                guard(resolved)
                shutil.rmtree(resolved)
                item['status']='removed';save()
                print('Removed',flush=True)
        result['status']='complete'
    except BaseException as exc:
        result.update(status='failed',error=str(exc));raise
    finally:
        result['free_after']={'D':shutil.disk_usage('D:/').free,'Z':shutil.disk_usage(ARCHIVE).free}
        save();print('Audit: '+str(audit),flush=True)

if __name__=='__main__': main()
