"""Fill empty saved Players Stats photos only; retain all operator text and edits."""
import argparse
import base64
import copy
import getpass
import json
import os
from pathlib import Path

from import_davis_players import atomic_json, request_json
from publish_davis_presets import identity


def run(args):
    report = json.loads(args.review.read_text(encoding='utf-8'))
    password = os.environ.get('SCOREBOARD_EDITOR_PASSWORD') or getpass.getpass('Host editor password: ')
    results = []
    before = request_json(args.server + '/api/templates')
    if before.get('warnings'):
        raise ValueError('Library needs attention; no updates made')
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output/'library-before.json', before)
    for row in report['players']:
        entries = request_json(args.server + '/api/templates')
        if entries.get('warnings'):
            raise ValueError('Library needs attention; stopped')
        target = dict(template='t6', country=row['country'], player=row['name'])
        matches = [x for x in entries['templates'] if identity(x) == identity(target)]
        if len(matches) != 1:
            raise ValueError('Ambiguous or missing preset: ' + row['name'])
        item = matches[0]
        if item['config'].get('player_path'):
            result = dict(name=row['name'], id=item['id'], status='existing-photo-preserved')
        else:
            path = (args.review.parent/row['image_file']).resolve()
            if args.review.parent.resolve() not in path.parents:
                raise ValueError('Photo outside review folder')
            uploaded = request_json(args.server + '/api/upload', dict(name=path.name,
                data='data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')))
            config = copy.deepcopy(item['config'])
            config['player_path'] = uploaded['path']
            saved = request_json(args.server + '/api/templates/update', dict(id=item['id'],
                edit_revision=item['edit_revision'], config=config, username=args.username, password=password))['item']
            assert {k:v for k,v in saved['config'].items() if k!='player_path'} == {
                k:v for k,v in item['config'].items() if k!='player_path'}
            result = dict(name=row['name'], id=item['id'], status='photo-added',
                source=row['field_sources']['player_path'], edit_revision=saved['edit_revision'])
        results.append(result)
        atomic_json(args.output/'results.json', results)
        print(row['name'] + ': ' + result['status'], flush=True)
    atomic_json(args.output/'library-after.json', request_json(args.server + '/api/templates'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--server', default='http://127.0.0.1:8080')
    parser.add_argument('--username', default='veto')
    run(parser.parse_args())
