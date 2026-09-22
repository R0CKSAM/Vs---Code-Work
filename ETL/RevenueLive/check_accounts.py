"""Exercise real admin/client browsers against an isolated database."""
from pathlib import Path
from contextlib import closing
import secrets
import sqlite3
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
from werkzeug.security import generate_password_hash
from app import create_app

data = ROOT / '.test-data' / secrets.token_hex(8)
app = create_app(data)
password = secrets.token_urlsafe(18)
temporary = secrets.token_urlsafe(18)
replacement = secrets.token_urlsafe(18)
with closing(sqlite3.connect(data / 'revenuelive.db')) as db, db:
    db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')", ('admin', generate_password_hash(password)))
    db.executemany('INSERT INTO channels VALUES (?,?)', [(1, 'Alpha'), (2, 'Beta')])
    db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)', [('2026-09-20', 1, 1, 2, 100, 0, 100, 'seed'), ('2026-09-20', 2, 10, 20, 900, 0, 900, 'seed')])
server = create_server(app, host='127.0.0.1', port=0)
threading.Thread(target=server.run, daemon=True).start()
url = 'http://127.0.0.1:' + str(server.effective_port)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        admin = browser.new_page()
        client = browser.new_page()
        errors = []
        for page in (admin, client):
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)

        def login(page, username, secret):
            page.locator('#loginForm [name=username]').fill(username)
            page.locator('#loginForm [name=password]').fill(secret)
            page.locator('#loginForm button.primary').click()

        def save():
            admin.locator('#userForm button.primary').click()
            expect(admin.locator('#userDialog')).not_to_be_visible()

        def edit():
            admin.locator('#users tr').filter(has_text='client').get_by_role('button', name='Edit').click()

        login(admin, 'admin', password)
        admin.locator('#adminNav').click()
        admin.locator('#addUser').click()
        admin.locator('#userForm [name=username]').fill('client')
        admin.locator('#userForm [name=password]').fill(temporary)
        admin.locator('#assignAll').click()
        expect(admin.locator('#assignments input:checked')).to_have_count(2)
        admin.locator('#assignmentSearch').fill('Alpha')
        admin.locator('#assignClear').click()
        expect(admin.locator('#assignments input:checked')).to_have_count(0)
        admin.locator('#assignShown').click()
        expect(admin.locator('#assignments input:checked')).to_have_count(1)
        for width in (320, 390, 1440):
            admin.set_viewport_size({'width': width, 'height': 900})
            assert admin.evaluate('document.documentElement.scrollWidth <= innerWidth')
        save()
        login(client, ' CLIENT ', temporary)
        expect(client.locator('#passwordDialog')).to_be_visible()
        client.locator('#passwordForm [name=current]').fill(temporary)
        client.locator('#passwordForm [name=password]').fill(replacement)
        client.locator('#passwordForm [name=confirm]').fill(replacement)
        client.locator('#passwordForm button.primary').click()
        expect(client.locator('#passwordDialog')).not_to_be_visible()
        expect(client.locator('#records')).to_contain_text('Alpha')
        expect(client.locator('#records')).not_to_contain_text('Beta')
        assert client.request.get(url + '/api/report?channel=2').status == 400

        edit()
        admin.locator('#assignAll').click()
        save()
        expect(client.locator('#records')).to_contain_text('Beta', timeout=8000)
        edit()
        admin.locator('#assignments input[value="1"]').uncheck()
        save()
        expect(client.locator('#records')).not_to_contain_text('Alpha', timeout=8000)
        expect(client.locator('#records')).to_contain_text('Beta')
        assert 'Alpha' not in client.request.get(url + '/api/export').text()
        edit()
        admin.locator('#assignClear').click()
        save()
        expect(client.locator('#records tr')).to_have_count(0, timeout=8000)
        edit()
        admin.locator('#assignAll').click()
        admin.locator('#userForm [name=role]').select_option('uploader')
        save()
        expect(client.locator('#uploadNav')).to_be_visible(timeout=8000)
        expect(client.locator('#records')).to_contain_text('Alpha')
        edit()
        admin.locator('#userForm [name=role]').select_option('viewer')
        save()
        expect(client.locator('#uploadNav')).not_to_be_visible(timeout=8000)
        edit()
        admin.locator('#userForm [name=active]').uncheck()
        save()
        expect(client.locator('#login')).to_be_visible(timeout=8000)
        expect(client.locator('#records tr')).to_have_count(0)
        assert client.request.get(url + '/api/report').status == 401
        edit()
        admin.locator('#userForm [name=active]').check()
        save()
        login(client, 'client', replacement)
        expect(client.locator('#records')).to_contain_text('Alpha')
        edit()
        admin.locator('#userForm [name=password]').fill(temporary)
        save()
        expect(client.locator('#login')).to_be_visible(timeout=8000)
        login(client, 'client', temporary)
        expect(client.locator('#passwordDialog')).to_be_visible()
        assert not errors, errors
        import json
        import re
        from unittest.mock import patch
        (data/'mail.json').write_text(json.dumps({'public_url':'https://revenue.example.com','host':'smtp.example.com','from':'sender@example.com'}))
        admin.locator('#addUser').click()
        admin.locator('#inviteEmail').check()
        admin.locator('#userForm [name=username]').fill('invited@gmail.com')
        admin.locator('#assignAll').click()
        with patch('account_email.smtplib.SMTP') as smtp:
            save()
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            token=re.search(r'account-token=([^\s]+)',message.get_content())[1]
        invited=browser.new_page(viewport={'width':390,'height':844})
        invited.on('pageerror',lambda error:errors.append(str(error)))
        invited.goto(url+'/#account-token='+token)
        expect(invited.locator('#accountDialog')).to_be_visible()
        assert '#' not in invited.url
        invited.locator('#accountForm [name=password]').fill(replacement)
        invited.locator('#accountForm [name=confirm]').fill(replacement)
        invited.locator('#accountForm button.primary').click()
        expect(invited.locator('#accountDialog')).not_to_be_visible()
        login(invited,'invited@gmail.com',replacement)
        expect(invited.locator('#records')).to_contain_text('Alpha')
        assert invited.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print('PASS: invitation UI, setup link, hidden token and mobile invited-user login (mock SMTP).')
        print('PASS: creation, bulk selection, mobile fit, first login, password setup, live grants/revocation, zero access, role changes, disable/re-enable, reset revocation, scoped export.')
        browser.close()
finally:
    server.close()
