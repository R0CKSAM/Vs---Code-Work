import importlib.util
import json
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'recorder/recorder_server.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('library_server_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    channels = tmp_path / 'channels.json'
    channels.write_text('[]')
    manager = module.RecorderManager(channels, tmp_path / 'recordings', tmp_path / 'state.sqlite')
    module.RecorderHandler.manager = manager
    server = module.ThreadingHTTPServer(('127.0.0.1', 0), module.RecorderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield manager, f'http://127.0.0.1:{server.server_port}'
    manager.shutdown()
    server.shutdown()
    server.server_close()
    thread.join()


def add_recording(manager, name='Test', status='stopped', folder=None):
    folder = folder or manager.recordings_dir / '2026-09-13' / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{name}_part_000.mkv'
    path.write_bytes(b'0123456789')
    manager.store.insert(dict(id=name, channel_id=name, channel_name=name,
        status=status, started_at='2026-09-13T12:00:00+05:30',
        output_pattern=str(folder / f'{name}_part_%03d.mkv'), pid=0, error=''))
    return path


def test_download_ranges_and_access_boundaries(recorder, tmp_path):
    manager, base = recorder
    add_recording(manager)
    add_recording(manager, 'Active', 'recording')
    add_recording(manager, 'Outside', folder=tmp_path / 'outside')
    with urlopen(base + '/api/library') as response:
        data = json.load(response)['files']
    assert len(data) == 1 and data[0]['channel'] == 'Test'
    assert not any(key.startswith('_') for key in data[0])
    url = base + '/api/library/' + data[0]['id'] + '/download'
    with urlopen(url) as response:
        assert response.read() == b'0123456789'
        assert 'attachment' in response.headers['Content-Disposition']
    for value, expected in [('bytes=2-5', b'2345'), ('bytes=-3', b'789'), ('bytes=8-', b'89')]:
        with urlopen(Request(url, headers={'Range': value})) as response:
            assert response.status == 206
            assert response.read() == expected
    with urlopen(Request(url, method='HEAD')) as response:
        assert response.headers['Content-Length'] == '10'
        assert response.read() == b''
    for value in ['bytes=99-', 'bytes=-0', 'bytes=4-2', 'bytes=0-1,4-5']:
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, headers={'Range': value}))
        assert error.value.code == 416
    for route in ['/channels.json', '/recorder_state.sqlite', '/recordings/',
                  '/api/library/../../channels.json/download', '/api/library/' + '0' * 64 + '/download']:
        with pytest.raises(HTTPError) as error:
            urlopen(base + route)
        assert error.value.code == 404


def test_browser_conversion_preserves_original(recorder):
    manager, base = recorder
    if not manager.ffmpeg:
        pytest.skip('FFmpeg unavailable')
    original = add_recording(manager)
    subprocess.run([manager.ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=160x90:rate=10', '-t', '1', '-c:v', 'libx264',
                    str(original)], check=True, timeout=30)
    before = original.read_bytes()
    token = manager.library.files()[0]['id']
    endpoint = base + '/api/library/' + token
    with urlopen(Request(endpoint + '/preview', data=b'{}', headers={'Content-Type': 'application/json'})) as response:
        assert json.load(response)['state'] == 'preparing'
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = manager.library.preview(token)
        if state['state'] != 'preparing':
            break
        time.sleep(0.1)
    assert state['state'] == 'ready', state
    assert original.read_bytes() == before
    with urlopen(Request(endpoint + '/video', headers={'Range': 'bytes=0-31'})) as response:
        assert response.status == 206
        assert response.headers['Content-Type'] == 'video/mp4'
        assert b'ftyp' in response.read()
    assert manager.library.preview(token, start=True) == {'state': 'ready'}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route('https://cdn.jsdelivr.net/**', lambda route: route.fulfill(body=''))
        page.goto(base)
        page.locator('#libraryRows button[data-play]').click()
        page.wait_for_function("document.getElementById('savedVideo').videoWidth === 160")
        page.evaluate("document.getElementById('savedVideo').currentTime = 0.5")
        page.wait_for_function("Math.abs(document.getElementById('savedVideo').currentTime - 0.5) < 0.1 || document.getElementById('savedVideo').ended")
        browser.close()


def test_library_browser_controls(recorder, tmp_path):
    from playwright.sync_api import sync_playwright

    manager, base = recorder
    add_recording(manager)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        # No live feeds or external CDN dependencies are needed for library tests.
        page.route('https://cdn.jsdelivr.net/**', lambda route: route.fulfill(body=''))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width, height in [(1440, 1000), (390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.goto(base)
            page.locator('#libraryRows button[data-play]').wait_for()
            assert page.locator('#libraryRows tr').count() == 1
            page.locator('#libraryDate').fill('2020-01-01')
            page.locator('#libraryDate').dispatch_event('change')
            assert 'No completed files' in page.locator('#libraryRows').inner_text()
            page.locator('#libraryClear').click()
            with page.expect_download() as download:
                page.locator('#libraryRows a').click()
            assert Path(download.value.path()).read_bytes() == b'0123456789'
            page.locator('#libraryRows button[data-play]').click()
            assert page.locator('#playDialog').is_visible()
            page.locator('#playClose').click()
            assert not page.locator('#playDialog').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(tmp_path / f'library-{width}.png'), full_page=True)
        assert not errors
        browser.close()
