"""Host-only, idempotent provisioning; never resets an existing password."""
import argparse
from contextlib import closing
import datetime as dt
from pathlib import Path
import secrets
import sqlite3
from werkzeug.security import generate_password_hash
from app import create_app


def provision(data, username):
    create_app(data)
    with closing(sqlite3.connect(data/'revenuelive.db')) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        owner=db.execute('SELECT u.username FROM super_admin s JOIN users u ON u.id=s.user_id').fetchone()
        if owner:
            if owner[0].casefold()!=username.casefold():
                raise ValueError('A different Super Admin already exists; no changes made.')
            print(str(data)+': Super Admin already configured; password unchanged.')
            return
        user=db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
        if user:
            uid=user[0]
            db.execute("UPDATE users SET role='admin',active=1 WHERE id=?",(uid,))
        else:
            password=secrets.token_urlsafe(24)
            credentials=data/'super_admin_initial.txt'
            with credentials.open('x',encoding='utf-8') as handle:
                handle.write('Username: '+username+'\nTemporary password: '+password+'\nChange on first login. Keep private; delete after changing.\n')
            uid=db.execute("INSERT INTO users(username,password,role,must_change) VALUES (?,?,'admin',1)",(username,generate_password_hash(password))).lastrowid
        db.execute('INSERT INTO super_admin VALUES (1,?)',(uid,))
        db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        db.execute('INSERT INTO audit(created,user_id,action,detail) VALUES (?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),uid,'super_admin_provisioned','Host-only provisioning'))
    print(str(data)+': Super Admin configured. Existing account passwords were not reset.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--username',required=True)
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args()
    provision(Path(__file__).resolve().parent/('demo_data' if args.demo else 'data'),args.username)
