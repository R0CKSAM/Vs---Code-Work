"""Destructive smoke test for a disposable, already migrated MariaDB database."""
import io
from contextlib import closing
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import generate_password_hash

from app import HEADERS, create_app, verify_audit_chain
from deploy import reset_super_admin


def main():
    app = create_app()
    app.testing = True
    database = app.extensions['database']
    with closing(database.connect()) as connection, connection:
        connection.begin_write()
        password = 'mysql-smoke-password'
        admin = connection.execute("INSERT INTO users(username,password,role,must_change) VALUES (?,?,'admin',0)",
                                   ('smoke-admin', generate_password_hash(password))).lastrowid
        viewer = connection.execute("INSERT INTO users(username,password,role,must_change) VALUES (?,?,'viewer',0)",
                                    ('smoke-viewer', generate_password_hash(password))).lastrowid
        channel = connection.execute("INSERT INTO channels(name) VALUES ('Smoke Channel')").lastrowid
        connection.execute('INSERT INTO assignments VALUES (?,?)', (viewer, channel))
        connection.execute('INSERT INTO super_admin VALUES (1,?)', (admin,))

    client = app.test_client()
    response = client.post('/api/login', json={'username':'smoke-admin', 'password':password})
    assert response.status_code == 200, response.json
    csrf = client.get('/api/me').json['csrf']
    headers = {'X-CSRF-Token':csrf}
    content = (','.join(HEADERS) + '\n2026-09-30,Smoke Channel,100,50,1.00,2.00,3.00\n').encode()
    response = client.post('/api/uploads/preview', data={'file':(io.BytesIO(content),'smoke.csv')}, headers=headers)
    assert response.status_code == 200, response.json
    upload = response.json['id']
    assert client.post(f'/api/uploads/{upload}/commit', json={}, headers=headers).status_code == 200
    assert client.get('/api/report').json['totals']['total'] == 300
    assert client.post(f'/api/uploads/{upload}/archive', json={'archived':True}, headers=headers).status_code == 200
    assert client.get('/api/report').json['rows'] == []
    assert client.post(f'/api/uploads/{upload}/unarchive', json={}, headers=headers).status_code == 200
    assert client.get('/api/report').json['totals']['total'] == 300
    client.post('/api/logout', json={}, headers=headers)
    assert client.post('/api/login', json={'username':'smoke-viewer','password':password}).status_code == 200
    assert client.get('/api/admin/users').status_code == 403
    assert client.get('/api/report').json['totals']['total'] == 300
    reset_super_admin(database, 'recovered-owner', 'recovered-password-123')
    recovered = app.test_client()
    assert recovered.post('/api/login', json={
        'username':'recovered-owner', 'password':'recovered-password-123'}).status_code == 200
    identity = recovered.get('/api/me').json
    assert identity['user']['super_admin'] is True
    assert identity['user']['must_change'] == 1
    assert recovered.get('/api/admin/users').status_code == 403
    with closing(database.connect()) as connection:
        assert verify_audit_chain(connection)[0]
    database.engine.dispose()
    print('MariaDB application smoke test: PASS')


if __name__ == '__main__':
    main()
