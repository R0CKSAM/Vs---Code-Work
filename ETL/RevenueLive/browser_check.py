"""Isolated browser smoke test; never writes production data."""
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from contextlib import closing

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
from werkzeug.security import generate_password_hash
from app import create_app, parse_upload

data=ROOT/'.test-data'/secrets.token_hex(8)
app=create_app(data)
password=secrets.token_urlsafe(18)
with closing(sqlite3.connect(data/'revenuelive.db')) as db, db:
    db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')",('test-admin',generate_password_hash(password)))
    for row in parse_upload((ROOT/'Upload File.xls').read_bytes(),'.xls'):
        db.execute('INSERT OR IGNORE INTO channels(name) VALUES (?)',(row['channel'],))
server=create_server(app,host='127.0.0.1',port=0)
thread=threading.Thread(target=server.run,daemon=True)
thread.start()
url='http://127.0.0.1:'+str(server.effective_port)
screens=ROOT/'.screenshots'
screens.mkdir(exist_ok=True)
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto(url)
        page.locator('#loginForm [name=username]').fill('test-admin')
        page.locator('#loginForm [name=password]').fill(password)
        page.locator('#loginForm button').click()
        page.locator('#shell').wait_for(state='visible')
        page.locator('#uploadNav').click()
        page.locator('input[type=file]').set_input_files(str(ROOT/'Upload File.xls'))
        page.locator('#uploadForm button').click()
        page.locator('#preview').wait_for(state='visible')
        assert '28 rows' in page.locator('#previewCount').inner_text()
        page.on('dialog',lambda d:d.accept())
        page.locator('#publish').click()
        expect(page.locator('#history')).to_contain_text('committed')
        page.locator('[data-view=dashboard]').click()
        expect(page.locator('#total')).to_contain_text('313.89')
        assert '1,49,938' in page.locator('#views').inner_text()
        page.screenshot(path=str(screens/'desktop.png'),full_page=True)
        for width in [390,360,768]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            page.screenshot(path=str(screens/f'mobile-{width}.png'),full_page=True)
        page.locator('#adminNav').click()
        page.locator('#addUser').click()
        page.locator('#userForm [name=username]').fill('Mobile Viewer')
        page.locator('#userForm [name=password]').fill('temporary-viewer-password')
        page.locator('#assignments input').first.check()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(screens/'user-dialog.png'))
        page.locator('#userForm button[type=submit], #userForm button.primary').click()
        expect(page.locator('#users')).to_contain_text('Mobile Viewer')
        assert not errors,errors
        print(json.dumps({'sample_published':True,'total_inr':313.89,'mobile_widths':[360,390,768],'user_created':True,'page_errors':errors}))
        browser.close()
finally:
    server.close()
