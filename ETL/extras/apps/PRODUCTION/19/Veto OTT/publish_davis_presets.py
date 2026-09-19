"""Create-only Davis Cup library import. Never starts, stops, or takes SDI live."""
import argparse
import base64
import copy
import csv
import io
import json
from pathlib import Path
import time

import scoreboard_app as core
from import_davis_players import COUNTRIES, atomic_json, country_name, key, request_json, scraper_values


def display_country(country):
    return 'KOREA' if country_name(country) == 'South Korea' else country_name(country).upper()


def identity(item):
    return item['template'], country_name(item['country']), key(item['player'])


def build_items(report, photo_reports, scraper_csv):
    photo_rows = {}
    for path in photo_reports:
        for row in json.loads(path.read_text(encoding='utf-8'))['players']:
            if row.get('image_file'):
                image = Path(row['image_file'])
                photo_rows[row['profile_id']] = image if image.is_absolute() else path.parent / image
    with scraper_csv.open(encoding='utf-8-sig', newline='') as stream:
        source_rows = list(csv.DictReader(stream))
    items = []
    for row in report['players']:
        if row.get('role') != 'player':
            continue
        cfg = copy.deepcopy(row['config'])
        # Official profile UUID resolves the roster's shortened name to Portero.
        if row['profile_id'] == 'b32d3c90-e208-4510-a09b-95561ea6fcf4':
            matches = [x for x in source_rows if country_name(x['COUNTRY']) == 'Spain'
                       and key(x['NAME']) == key('Pedro Martinez Portero')]
            values, issues = scraper_values(matches)
            if issues:
                raise ValueError('Pedro Martinez Portero CSV requires review: ' + '; '.join(issues))
            cfg.update(values)
        cfg.update(country=display_country(row['country']), player_name=row['name'])
        cfg['player_path'] = ''
        items.append(dict(template='t6', player=row['name'], country=cfg['country'], config=cfg,
                          photo=str(photo_rows.get(row['profile_id'], '')), profile_id=row['profile_id']))
    for country in COUNTRIES:
        label = display_country(country)
        config = copy.deepcopy(core.DEF_T7)
        config.update(country_a=label, country_b='', score='',
                      rows=[{'value_a': '', 'value_b': ''} for _ in range(5)])
        items.append(dict(template='t7', player=label + ' - Qualifier Rounds', country=label, config=config))
    if len({identity(item) for item in items}) != len(items):
        raise ValueError('Duplicate batch identities')
    return items


def run(args):
    report = json.loads(args.review.read_text(encoding='utf-8'))
    items = build_items(report, args.photos, args.scraper_csv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshot = request_json(args.server + '/api/templates')
    if snapshot.get('warnings'):
        raise ValueError('Library warnings: refusing batch publication')
    atomic_json(out / 'library-before.json', snapshot)
    atomic_json(out / 'import-plan.json', items)
    if not args.publish:
        print('Preview plan only: ' + str(out / 'import-plan.json'))
        return
    results = []
    for item in items:
        current = request_json(args.server + '/api/templates')
        if current.get('warnings'):
            raise ValueError('Library became unreadable; stopped')
        existing = next((x for x in current['templates'] if identity(x) == identity(item)), None)
        if existing:
            result = dict(status='existing-untouched', id=existing['id'])
        else:
            cfg = copy.deepcopy(item['config'])
            if item.get('photo'):
                path = Path(item['photo'])
                with core.Image.open(path) as image:
                    image.load()
                    if image.mode != 'RGBA' or image.getchannel('A').getextrema() != (0, 255):
                        raise ValueError('Invalid cutout: ' + str(path))
                    data = io.BytesIO()
                    image.save(data, format='PNG')
                uploaded = request_json(args.server + '/api/upload', dict(name=path.name,
                    data='data:image/png;base64,' + base64.b64encode(data.getvalue()).decode('ascii')))
                cfg['player_path'] = uploaded['path']
            response = request_json(args.server + '/api/templates/save', dict(
                template=item['template'], player=item['player'], country=item['country'], config=cfg))
            saved = response.get('item') if response.get('saved') else response['existing']
            result = dict(status='created' if response.get('saved') else 'existing-untouched', id=saved['id'])
        results.append(dict(template=item['template'], country=item['country'], player=item['player'], **result))
        atomic_json(out / 'results.json', results)
        print(item['country'] + ' / ' + item['player'] + ': ' + result['status'], flush=True)
    after = request_json(args.server + '/api/templates')
    atomic_json(out / 'library-after.json', after)
    by_id = {x['id']: x for x in after['templates']}
    for old in snapshot['templates']:
        if by_id.get(old['id']) != old:
            raise ValueError('Existing library entry changed during import; inspect snapshots: ' + old['id'])
    expected = {identity(x) for x in items}
    assert expected <= {identity(x) for x in after['templates']}
    print(json.dumps(dict(created=sum(x['status'] == 'created' for x in results),
        preserved=sum(x['status'] == 'existing-untouched' for x in results),
        players=sum(x['template'] == 't6' for x in results), country_presets=14,
        library_warnings=after.get('warnings', []), output=str(out)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--photos', type=Path, nargs='+', required=True)
    parser.add_argument('--scraper-csv', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--server', default='http://127.0.0.1:8080')
    parser.add_argument('--publish', action='store_true')
    run(parser.parse_args())
