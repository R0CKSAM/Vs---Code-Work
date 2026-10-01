"""Deployment settings; process environment takes precedence over .env."""
import os
import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent


def load_environment():
    load_dotenv(ROOT / '.env', override=False)


def boolean(name, default=False):
    value = os.environ.get(name, str(default)).lower()
    if value not in {'1', '0', 'true', 'false'}:
        raise ValueError(f'{name} must be true or false.')
    return value in {'1', 'true'}


def public_url(value, path=False):
    url = urlsplit(value)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or (not path and url.path not in ('', '/'))):
        raise ValueError('Public URLs must use HTTPS and contain no credentials, query or fragment.')
    url.port
    return value.rstrip('/')


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    upload_dir: Path
    app_url: str
    admin_url: str
    user_url: str
    portal_mode: str
    hosts: tuple
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    session_ttl: int
    db_url: URL

    @classmethod
    def from_env(cls, data_dir=None):
        load_environment()
        local = data_dir is not None
        data = Path(data_dir or os.environ.get('DATA_DIR') or os.environ.get('REVENUE_DATA_DIR', ROOT / 'data')).resolve()
        app_url = (os.environ.get('REVENUE_PUBLIC_URL', '') if local else
                   os.environ.get('APP_URL', os.environ.get('REVENUE_PUBLIC_URL', ''))).strip()
        if app_url:
            app_url = public_url(app_url)
        production = not local and os.environ.get('APP_ENV', 'development') == 'production'
        if (production or os.environ.get('REVENUE_HTTPS') == '1') and not app_url:
            raise ValueError('APP_URL (or REVENUE_PUBLIC_URL) is required for production HTTPS deployments.')
        mode = 'single' if local else os.environ.get('PORTAL_MODE', 'single')
        if mode not in {'single', 'split'}:
            raise ValueError('PORTAL_MODE must be single or split.')
        admin = os.environ.get('ADMIN_URL', app_url + '/admin' if app_url else '/admin')
        user = os.environ.get('USER_URL', app_url + '/user' if app_url else '/user')
        if app_url:
            admin, user = public_url(admin, True), public_url(user, True)
            if mode == 'single' and any(urlsplit(x).netloc != urlsplit(app_url).netloc for x in (admin, user)):
                raise ValueError('Single portal URLs must use the APP_URL host.')
            if mode == 'split' and urlsplit(admin).netloc == urlsplit(user).netloc:
                raise ValueError('Split portals need distinct ADMIN_URL and USER_URL hosts.')
            if any(urlsplit(x).path not in ('', '/', '/admin', '/user') for x in (admin, user)):
                raise ValueError('Panel URLs must use /admin, /user, or the host root.')
        elif mode == 'split':
            raise ValueError('Split portals require HTTPS public URLs.')
        expected = {urlsplit(x).hostname for x in (app_url, admin, user) if urlsplit(x).hostname}
        host_setting = ','.join(sorted(expected)) if local else os.environ.get('ALLOWED_HOSTS', ','.join(sorted(expected)))
        hosts = tuple(x.strip() for x in host_setting.split(',') if x.strip())
        if expected and not expected.issubset(set(hosts)):
            raise ValueError('ALLOWED_HOSTS must include every configured public hostname.')
        if any(not re.fullmatch(r'[A-Za-z0-9.-]+', host) or host.startswith('.') for host in hosts):
            raise ValueError('ALLOWED_HOSTS accepts exact hostnames only.')
        secure = bool(app_url) if local else boolean('SESSION_COOKIE_SECURE', bool(app_url))
        if app_url and not secure:
            raise ValueError('Public deployments require secure cookies.')
        same = 'Strict' if local else os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
        if same not in {'Strict', 'Lax'}:
            raise ValueError('SESSION_COOKIE_SAMESITE must be Strict or Lax.')
        default_cookie = 'revenuelive_session' if app_url else 'revenue_' + hashlib.sha256(str(data).encode()).hexdigest()[:12]
        cookie = default_cookie if local else os.environ.get('SESSION_COOKIE_NAME', default_cookie)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', cookie):
            raise ValueError('Invalid SESSION_COOKIE_NAME.')
        ttl = 28800 if local else int(os.environ.get('SESSION_TTL_SECONDS', '28800'))
        if not 300 <= ttl <= 86400:
            raise ValueError('SESSION_TTL_SECONDS must be between 300 and 86400.')
        # Passing data_dir is the explicit local/test SQLite API retained for compatibility.
        driver = 'sqlite' if data_dir is not None else os.environ.get('DB_DRIVER', 'sqlite')
        if driver == 'sqlite':
            if production:
                raise ValueError('Set DB_DRIVER=mysql+pymysql for production.')
            database = URL.create('sqlite', database=str(data / 'revenuelive.db'))
        elif driver in {'mysql+pymysql', 'mariadb+pymysql'}:
            required = ('DB_HOST', 'DB_DATABASE', 'DB_USERNAME', 'DB_PASSWORD')
            if any(not os.environ.get(key) for key in required):
                raise ValueError('MySQL requires DB_HOST, DB_DATABASE, DB_USERNAME and DB_PASSWORD.')
            database = URL.create(driver, host=os.environ['DB_HOST'], port=int(os.environ.get('DB_PORT', '3306')),
                                  database=os.environ['DB_DATABASE'], username=os.environ['DB_USERNAME'],
                                  password=os.environ['DB_PASSWORD'], query={'charset': 'utf8mb4'})
        else:
            raise ValueError('DB_DRIVER must be sqlite, mysql+pymysql, or mariadb+pymysql.')
        upload_dir = data / 'uploads' if local else Path(os.environ.get('UPLOAD_DIR', data / 'uploads'))
        return cls(data, upload_dir.resolve(), app_url,
                   admin, user, mode, hosts, cookie, secure, same, ttl, database)

    def request_origin(self, host):
        for value in (self.app_url, self.admin_url, self.user_url):
            url = urlsplit(value)
            if url.netloc.lower() == host.lower():
                return f'{url.scheme}://{url.netloc}'
        return ''

    def admin_host(self, host):
        return self.portal_mode == 'single' or host.lower() == urlsplit(self.admin_url).netloc.lower()
