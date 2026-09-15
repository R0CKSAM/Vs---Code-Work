"""Copy and verify a portable data snapshot without modifying source files."""
import hashlib
import json
import shutil
import sys
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def inventory(root):
    paths=[]
    for directory in ('uploads','projects','templates'):
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix!='.tmp')
    for name in ('editor_credentials.json','delete_credentials.json'):
        if (root/name).is_file(): paths.append(root/name)
    return {str(p.relative_to(root)):digest(p) for p in sorted(paths)}


def snapshot(source,target):
    source,target=Path(source).resolve(),Path(target).resolve()
    if not source.is_dir() or source==target or source in target.parents:
        raise ValueError('Choose a separate existing source data directory.')
    target.mkdir(parents=True,exist_ok=True)
    if any(target.rglob('*.*')):
        raise ValueError('Use a fresh destination to prevent stale presets or media being merged.')
    before=inventory(source)
    if not before: raise ValueError('No saved data found in source directory.')
    for name in before:
        path=source/name
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('Linked files outside source are not portable: '+name)
        out=target/name
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,out)
    if inventory(source)!=before or inventory(target)!=before:
        raise RuntimeError('Data changed during the copy. Retry in a fresh folder while saves are paused.')
    (target/'migration_manifest.json').write_text(json.dumps({'files':before},indent=2),encoding='utf-8')
    print(f'Verified {len(before)} data files, including media, presets and credentials.')


if __name__=='__main__':
    snapshot(*sys.argv[1:])
