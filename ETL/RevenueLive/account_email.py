"""Single-use email verification/password setup for explicitly invited accounts."""
import hashlib
import json
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlsplit

from flask import jsonify, request
from werkzeug.security import generate_password_hash


def install(app, db, data, invalid):
    with app.app_context():
        db().executescript('''
            CREATE TABLE IF NOT EXISTS email_accounts(user_id INTEGER PRIMARY KEY REFERENCES users(id), email TEXT UNIQUE COLLATE NOCASE NOT NULL, verified INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS email_tokens(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS email_limits(key TEXT PRIMARY KEY, expires REAL NOT NULL);
        ''')
        db().commit()

    def address(value):
        value = str(value).strip().lower()
        if len(value) > 80 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            raise invalid('Enter a valid email address (maximum 80 characters).')
        return value

    def settings():
        try:
            config = json.loads((data / 'mail.json').read_text(encoding='utf-8'))
            url = urlsplit(config['public_url'])
            if url.scheme != 'https' or not url.netloc or url.username or url.query or url.fragment:
                raise ValueError()
            if not config['host'] or not config['from']:
                raise ValueError()
            return config
        except (OSError, ValueError, KeyError):
            raise invalid('Email delivery is not configured. Ask the host administrator to configure mail.json with an HTTPS public URL.')

    def issue(uid):
        config = settings()
        user = db().execute('SELECT e.email FROM email_accounts e JOIN users u ON u.id=e.user_id WHERE u.id=? AND u.active=1', (uid,)).fetchone()
        if not user:
            raise invalid('No active email account found.')
        raw = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        db().execute('DELETE FROM email_tokens WHERE user_id=? OR expires<?', (uid, time.time()))
        db().execute('INSERT INTO email_tokens VALUES (?,?,?)', (digest, uid, time.time()+1800))
        db().commit()
        message = EmailMessage()
        message['Subject'] = 'RevenueLive: set your password'
        message['From'] = config['from']
        message['To'] = user['email']
        message.set_content('Set your RevenueLive password using this single-use link (expires in 30 minutes):\n\n'+config['public_url'].rstrip('/')+'/#account-token='+raw+'\n\nIf you did not request this, ignore this email. Never share this link.')
        try:
            with smtplib.SMTP(config['host'], int(config.get('port',587)), timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if config.get('username'):
                    smtp.login(config['username'], config['password'])
                smtp.send_message(message)
        except Exception:
            db().execute('DELETE FROM email_tokens WHERE token=?', (digest,))
            db().commit()
            raise invalid('Email could not be delivered. The account remains saved; use Forgot password after the host fixes email delivery.')

    @app.post('/api/account/request')
    def request_reset():
        settings()
        email = address((request.get_json(silent=True) or {}).get('email',''))
        key = 'ip:'+str(request.remote_addr)
        db().execute('BEGIN IMMEDIATE')
        now = time.time()
        limit = db().execute('SELECT expires FROM email_limits WHERE key=?', (key,)).fetchone()
        if limit and limit['expires'] > now:
            db().rollback()
            return jsonify(error='Wait a minute before requesting another link.'),429
        db().execute('INSERT OR REPLACE INTO email_limits VALUES (?,?)',(key,now+60))
        db().commit()
        user = db().execute('SELECT e.user_id FROM email_accounts e JOIN users u ON u.id=e.user_id WHERE e.email=? AND u.active=1', (email,)).fetchone()
        if user:
            try:
                issue(user['user_id'])
            except invalid:
                # Do not reveal whether a requested email is registered.
                app.logger.warning('Account email delivery failed; check host mail configuration.')
        return jsonify(ok=True, message='If this email has access, a password link will arrive shortly.')

    @app.post('/api/account/complete')
    def complete():
        body = request.get_json(silent=True) or {}
        password = str(body.get('password',''))
        if not 12 <= len(password) <= 256:
            raise invalid('Password must be 12 to 256 characters.')
        raw = str(body.get('token',''))
        if len(raw) > 100:
            raise invalid('Invalid or expired link.')
        digest = hashlib.sha256(raw.encode()).hexdigest()
        db().execute('BEGIN IMMEDIATE')
        token = db().execute('SELECT t.user_id FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE t.token=? AND t.expires>? AND u.active=1', (digest,time.time())).fetchone()
        if not token:
            raise invalid('Invalid or expired link. Request a new one.')
        uid = token['user_id']
        db().execute('UPDATE users SET password=?,must_change=0 WHERE id=?',(generate_password_hash(password),uid))
        db().execute('UPDATE email_accounts SET verified=1 WHERE user_id=?',(uid,))
        db().execute('DELETE FROM email_tokens WHERE user_id=?',(uid,))
        db().execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        db().commit()
        return jsonify(ok=True)

    return address, settings, issue
