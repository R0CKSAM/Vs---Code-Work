"""Export legacy project data without credential records for a Git backup."""
import json
import os
import re
import uuid
from pathlib import Path


PRIVATE_FIELDS = frozenset({
    '_edit_password', 'password', 'password_record', 'credentials', 'secret',
    'token', 'access_token', 'refresh_token', 'authorization', 'cookie',
})


def sanitized(value):
    if isinstance(value,dict):
        return {key:sanitized(child) for key,child in value.items()
                if key.casefold() not in PRIVATE_FIELDS}
    if isinstance(value,list):
        return [sanitized(child) for child in value]
    return value


def export_projects(app_dir):
    app_dir = Path(app_dir).resolve()
    source = app_dir/'data'/'projects'
    destination = app_dir/'project_exports'
    destination.mkdir(parents=True,exist_ok=True)
    count = 0
    for path in sorted(source.glob('*.json')):
        document = json.loads(path.read_text(encoding='utf-8-sig'))
        if not re.fullmatch(r'[a-f0-9]{32}',path.stem) or document.get('id') != path.stem:
            raise ValueError('Invalid project identity: ' + path.name)
        target = destination/path.name
        temporary = target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('w',encoding='utf-8') as stream:
                json.dump(sanitized(document),stream,ensure_ascii=False,indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
        count += 1
    return count


if __name__=='__main__':
    print('Exported',export_projects(Path(__file__).parent),'legacy projects without credentials.')
