"""Take an explicit database backup, including upload rows and audit history."""
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
from app import backup_database
from config import Settings

root=Path(__file__).resolve().parent
settings=Settings.from_env()
if settings.db_url.get_backend_name() == 'sqlite':
    target=backup_database(settings.data_dir)
else:
    backup_root=Path(os.environ.get('REVENUE_BACKUP_DIR',settings.data_dir.parent/'RevenueLive-backups')).resolve()
    if backup_root == settings.data_dir or backup_root.is_relative_to(settings.data_dir):
        raise ValueError('Keep backups outside the RevenueLive data directory.')
    target=backup_root/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    target.mkdir(parents=True)
    executable=os.environ.get('MYSQLDUMP_PATH') or shutil.which('mysqldump')
    if not executable:
        raise FileNotFoundError('Set MYSQLDUMP_PATH to the MySQL/MariaDB mysqldump executable.')
    environment=os.environ.copy()
    environment['MYSQL_PWD']=settings.db_url.password or ''
    command=[executable,'--single-transaction','--routines','--triggers','--hex-blob',
             '--host',settings.db_url.host,'--port',str(settings.db_url.port or 3306),
             '--user',settings.db_url.username,settings.db_url.database]
    if os.environ.get('DB_SSL_CA'):
        command.insert(1,'--ssl-ca='+os.environ['DB_SSL_CA'])
    try:
        with (target/'database.sql').open('wb') as output:
            subprocess.run(command,stdout=output,stderr=subprocess.PIPE,env=environment,
                           check=True,timeout=1800)
        (target/'BACKUP_COMPLETE').write_text('Database dump completed. Upload rows are included in the database.\n',encoding='ascii')
    except Exception:
        (target/'BACKUP_FAILED').write_text('Backup did not complete. Do not restore this folder.\n',encoding='ascii')
        raise
print('Backup:',target)
