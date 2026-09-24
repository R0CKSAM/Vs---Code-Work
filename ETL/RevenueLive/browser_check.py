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
        expect(page.locator('#login h1')).to_have_text('Veto I Partners')
        page.wait_for_function("()=>getComputedStyle(document.body).backgroundImage==='none'")
        page.locator('#loginForm [name=username]').fill('test-admin')
        page.locator('#loginForm [name=password]').fill('incorrect-password')
        page.locator('#loginForm button.primary').click()
        expect(page.locator('#loginError')).to_be_visible()
        expect(page.locator('#loginForm button.primary')).to_be_enabled()
        assert 'Session ended' not in page.locator('#loginError').inner_text()
        for width in [1440,390,320]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('login',width)
            assert page.evaluate("getComputedStyle(document.body).backgroundImage==='none'"),('plain login background',width)
            page.screenshot(path=str(screens/f'login-{width}.png'),full_page=True)
        page.locator('.forgot-password').click()
        expect(page.locator('#accountForm')).to_be_visible()
        page.keyboard.press('Escape')
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('#loginForm [name=username]').fill('test-admin')
        page.locator('#loginForm [name=password]').fill(password)
        page.locator('#loginForm button.primary').click()
        page.locator('#shell').wait_for(state='visible')
        assert page.evaluate("getComputedStyle(document.body).backgroundImage.includes('linear-gradient')"), 'Dashboard keeps gradient'
        page.locator('#accountMenu summary').click()
        page.locator('#uploadNav').click()
        page.locator('input[type=file]').set_input_files(str(ROOT/'Upload File.xls'))
        page.locator('#uploadForm button').click()
        page.locator('#preview').wait_for(state='visible')
        assert '28 rows' in page.locator('#previewCount').inner_text()
        page.on('dialog',lambda d:d.accept())
        page.locator('#publish').click()
        expect(page.locator('#history')).to_contain_text('committed')
        page.locator('#accountMenu summary').click()
        page.locator('[data-view=dashboard]').click()
        expect(page.locator('#total')).to_contain_text('314')
        assert '1,49,938' in page.locator('#views').inner_text()
        page.screenshot(path=str(screens/'desktop.png'),full_page=True)
        for width in [390,360,768]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            page.screenshot(path=str(screens/f'mobile-{width}.png'),full_page=True)
        page.locator('#accountMenu summary').click()
        page.locator('#adminNav').click()
        page.locator('#addUser').click()
        page.locator('#userForm [name=username]').fill('Mobile Viewer')
        page.locator('#userForm [name=password]').fill('temporary-viewer-password')
        page.locator('#assignments input').first.check()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(screens/'user-dialog.png'))
        page.locator('#userForm button[type=submit], #userForm button.primary').click()
        expect(page.locator('#users')).to_contain_text('Mobile Viewer')
        for view in ['tabular','uploads','admin','diyGraphs','insightsView']:
            page.locator('#accountMenu summary').click()
            page.locator('[data-view='+view+']').click()
            for width in [1440,390]:
                page.set_viewport_size({'width':width,'height':950})
                page.wait_for_timeout(150)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(view,width)
                assert page.locator('.workspace').evaluate("el=>getComputedStyle(el).backgroundColor==='rgb(255, 255, 255)'"),(view,width,'opaque work surface')
                page.screenshot(path=str(screens/f'light-{view}-{width}.png'),full_page=True)
        assert not errors,errors
        page.locator('#accountMenu summary').click()
        page.locator('[data-view=diyGraphs]').click()
        expect(page.locator('#diyCanvas')).to_be_visible()
        expect(page.locator('#revenueHeader')).to_be_hidden()
        expect(page.locator('#diyChannelOptions input')).to_have_count(28)
        page.locator('#diyType').select_option('line')
        page.locator('#diySecond').select_option('views')
        assert page.evaluate("Chart.getChart('diyCanvas').data.datasets.length===2")
        page.locator('#diySecond').select_option('none')
        assert page.evaluate("Chart.getChart('diyCanvas').data.datasets.length===1")
        page.locator('#diySecond').select_option('other')
        page.locator('#diyChannels summary').click()
        page.locator('#diyClearChannels').click()
        expect(page.locator('#diyStatus')).to_contain_text('No data')
        page.locator('#diySearch').fill('NDTV India')
        page.locator('#diySelectAll').click()
        expect(page.locator('#diyChannelOptions input:checked')).to_have_count(1)
        page.locator('#diySearch').fill('')
        page.locator('#diySelectAll').click()
        page.locator('#diyChannels summary').click()
        page.locator('#diyStart').click()
        expect(page.locator('.diy-calendar.open .diy-date-data')).to_have_count(1)
        page.screenshot(path=str(screens/'diy-calendar.png'))
        page.locator('#diyStart').evaluate("input=>{input._flatpickr.setDate('2099-01-01',true);input._flatpickr.close();}")
        expect(page.locator('#diyStatus')).to_contain_text('No data')
        page.locator('#diyAllDates').click()
        for width in [1440,944,390]:
            page.set_viewport_size({'width':width,'height':950})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('diy',width)
            page.screenshot(path=str(screens/f'diy-{width}.png'),full_page=True)
        for kind in ['bar','line','grouped','mixed','pie']:
            page.locator('#diyType').select_option(kind)
            assert page.evaluate("!!Chart.getChart('diyCanvas')"),kind
        page.locator('#diyName').fill('My channel share')
        page.locator('#diyGroup').select_option('channel')
        expect(page.locator('.diy-share-row')).to_have_count(6)
        expect(page.locator('.diy-share-centre')).to_contain_text('Ad revenue')
        assert page.evaluate("Chart.getChart('diyCanvas').config.type==='doughnut'")
        page.locator('.diy-share-breakdown > button').click()
        expect(page.locator('.diy-share-row')).to_have_count(28)
        for width in [1440,944,390]:
            page.set_viewport_size({'width':width,'height':950})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('diy-share',width)
            page.screenshot(path=str(screens/f'diy-share-{width}.png'),full_page=True)
        page.locator('.diy-share-breakdown > button').click()
        page.locator('#diyFirst').select_option('other')
        expect(page.locator('#diyStatus')).to_contain_text('No positive values')
        page.locator('#diyFirst').select_option('ad')
        page.locator('#diyType').select_option('bar')
        expect(page.locator('.diy-share')).to_be_hidden()
        expect(page.locator('#diyCanvas')).to_be_visible()
        page.locator('#diyType').select_option('pie')
        page.locator('#diySave').click()
        expect(page.locator('#diyStatus')).to_have_text('Preset saved.')
        page.locator('#diySave').click()
        expect(page.locator('#diyStatus')).to_contain_text('already exists')
        page.locator('#diySaved').select_option(label='My channel share')
        expect(page.locator('#diyType')).to_have_value('pie')
        page.locator('#diyDelete').click()
        expect(page.locator('#diySaved option')).to_have_count(5)
        assert not errors,errors
        print(json.dumps({'sample_published':True,'total_inr':313.89,'mobile_widths':[360,390,768],'user_created':True,'page_errors':errors}))
        browser.close()
finally:
    server.close()
