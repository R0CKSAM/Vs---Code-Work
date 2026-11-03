"""Read-only browser audit of the currently published ASRUN dashboard."""
import functools
import http.server
import json
from pathlib import Path
import threading
import sys
import csv
from playwright.sync_api import sync_playwright

ETL = Path(__file__).resolve().parents[2]
OUTPUT = ETL / 'asrun_demo/output'
REPORT = ETL / 'output/validation/asrun_browser_audit.json'

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(OUTPUT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {'errors': [], 'failed_requests': [], 'checks': {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            page.on('pageerror', lambda e: report['errors'].append(str(e)))
            page.on('requestfailed', lambda r: report['failed_requests'].append({'url': r.url, 'failure': r.failure}))
            filename = sys.argv[1] if len(sys.argv) > 1 else 'asrun_delivery_demo.html'
            page.goto(f'http://127.0.0.1:{server.server_port}/{filename}', wait_until='load', timeout=120000)
            page.wait_for_function("typeof dashboardPageNeedsLoading==='function' && !dashboardPageNeedsLoading('audience')", timeout=180000)
            report['checks']['initial'] = page.evaluate("""() => ({master:masterDashboardRange(),youtube:youtubeDashboardRange(),mode:youtubeDateMode})""")
            report['checks']['target_initial'] = page.evaluate("""() => {const e=DATA.events.find(e=>e.event_id==='C0079134'&&e.on_air_start_ist.startsWith('2026-11-01T23:19')); return {event:e,youtube:youtubeDeliveryDetails(e)};}""")
            page.evaluate("""async () => { $('from').value='2026-11-01';$('to').value='2026-11-01';await loadAudienceDashboardData();$('youtubeFrom').value='2026-11-01';$('youtubeTo').value='2026-11-01';await loadYoutubeDashboardData();refreshAudienceFilters();render();} """)
            report['checks']['target_aligned'] = page.evaluate("""() => {const e=DATA.events.find(e=>e.event_id==='C0079134'&&e.on_air_start_ist.startsWith('2026-11-01T23:19'));return combinedRows([e],audienceMinuteMap('fast'),audienceMinuteMap('stream'))[0];}""")
            report['checks']['all_nov1_events'] = page.evaluate("""() => {const es=DATA.events.filter(e=>e.on_air_start_ist.startsWith('2026-11-01'));const rows=combinedRows(es,audienceMinuteMap('fast'),audienceMinuteMap('stream'));return {count:rows.length,missingYT:rows.filter(r=>r.youtube.total===null).length,missingStream:rows.filter(r=>r.stream.total===null).length,missingFast:rows.filter(r=>r.fast.total===null).length,badCombined:rows.filter(r=>r.missingSources.length&&r.total!==null).length};}""")
            with page.expect_download() as download:
                page.evaluate('exportAllEventsCsv()')
            export = ETL / 'output/validation/asrun_browser_export.csv'
            download.value.save_as(export)
            with export.open(encoding='utf-8-sig', newline='') as handle:
                exported = list(csv.DictReader(handle))
            target = next(row for row in exported if row['Ad ID'] == 'C0079134' and '11:19:24' in row['On-air IST'])
            report['checks']['csv_target'] = {k:v for k,v in target.items() if 'Concurrency' in k or k=='Coverage Status'}
            assert float(target['India TV YouTube Minute Concurrency']) == 3239
            missing = report['checks']['target_aligned']['missingSources']
            assert target['Coverage Status'] == ('Missing source data: '+', '.join(missing) if missing else 'All sources covered')
            report['checks']['recent_dates'] = {}
            for day in ('2026-10-29','2026-10-30','2026-10-31'):
                result = page.evaluate("""async day => {
                  $('from').value=day;$('to').value=day;await loadAudienceDashboardData();refreshAudienceFilters();
                  const es=DATA.events.filter(e=>e.on_air_start_ist.startsWith(day));
                  const rows=combinedRows(es,audienceMinuteMap('fast'),audienceMinuteMap('stream'));
                  return {events:rows.length,missingStream:rows.filter(r=>r.stream.total===null).length,
                    missingFast:rows.filter(r=>r.fast.total===null).length,missingYT:rows.filter(r=>r.youtube.total===null).length,
                    badTotals:rows.filter(r=>r.missingSources.length?r.total!==null:r.total!==r.fast.total+r.stream.total+r.amagi.total+r.youtube.total).length};
                }""", day)
                report['checks']['recent_dates'][day] = result
                assert result['badTotals'] == 0
                if day=='2026-10-31':
                    assert result['missingStream']==result['events']
            report['checks']['pages'] = {}
            for name in ('delivery', 'content', 'audience'):
                page.evaluate('(name)=>setDashboardPage(name)', name)
                page.wait_for_function('(name)=>!dashboardPageNeedsLoading(name)', arg=name, timeout=180000)
                report['checks']['pages'][name] = 'loaded'
            report['checks']['collector_semantics'] = page.evaluate("""() => {
              installDashboardPartition('youtube','2099-01-01',{collector_minute:[
                {timestamp_ist:'2099-01-01T12:00:00',youtube_channel:'India TV',collector_status:'no_live'},
                {timestamp_ist:'2099-01-01T12:01:00',youtube_channel:'India TV',collector_status:'lookup_error'}]});
              return {observedNoLive:youtubeDeliveryDetails({on_air_start_ist:'2099-01-01T12:00:00'}),
                lookupError:youtubeDeliveryDetails({on_air_start_ist:'2099-01-01T12:01:00'})};
            }""")
            assert not report['errors'], report['errors']
            assert not report['failed_requests'], report['failed_requests']
            assert report['checks']['target_initial']['youtube']['total'] == 3239
            expected_missing = page.evaluate("() => DATA.unavailable_viewer_days.filter(r=>r.date==='2026-11-01').map(r=>r.source.toUpperCase()).sort()")
            assert sorted(report['checks']['target_aligned']['missingSources']) == expected_missing
            assert report['checks']['all_nov1_events']['missingYT'] == 0
            assert report['checks']['all_nov1_events']['missingStream'] == 0
            assert report['checks']['all_nov1_events']['badCombined'] == 0
            assert report['checks']['collector_semantics']['observedNoLive']['total'] == 0
            assert report['checks']['collector_semantics']['lookupError']['total'] is None
            report['passed'] = True
            browser.close()
    finally:
        server.shutdown()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()
