"""Review and fill empty country Qualifier presets, without changing live output."""
import argparse
import copy
import getpass
import json
import os
from pathlib import Path

import scoreboard_app as core
from import_davis_players import COUNTRIES, atomic_json, country_name, request_json
from publish_davis_presets import display_country, identity


def validate_results(data):
    seen = set()
    for tie in data['ties']:
        if tie['a'] in seen or tie['b'] in seen or tie['a'] == tie['b']:
            raise ValueError('Duplicate country in draw')
        seen.update((tie['a'], tie['b']))
        wins = [0, 0]
        if len(tie['matches']) != 5:
            raise ValueError('Expected five ordered match slots')
        for match in tie['matches']:
            if not match:
                continue
            if len(match) != 2 or len(match[0]) != len(match[1]) or len(match[0]) not in (2, 3):
                raise ValueError('Invalid match shape')
            sets = [0, 0]
            for index, (a, b) in enumerate(zip(*match)):
                if any(type(v) is not int or v < 0 for v in (a, b)):
                    raise ValueError('Invalid set score')
                hi, lo = max(a, b), min(a, b)
                normal = (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))
                match_break = index == 2 and hi >= 10 and hi - lo >= 2
                if not (normal or match_break):
                    raise ValueError('Invalid completed set')
                if max(sets) == 2:
                    raise ValueError('Extra set after completed match')
                sets[int(b > a)] += 1
            if max(sets) != 2:
                raise ValueError('Incomplete match')
            wins[int(sets[1] > sets[0])] += 1
        if wins != tie['score'] or max(wins) < 3:
            raise ValueError('Match winners do not reconcile with tie total')
    if seen.intersection(data['byes']):
        raise ValueError('Bye country also played')


def config_for_country(data, country, set_scores=False):
    config = copy.deepcopy(core.DEF_T7)
    config.update(country_a=display_country(country), country_b='', score='', rows=[])
    country = country_name(country)
    if country in data['byes']:
        config.update(score='BYE', rows=[{'value_a':'', 'value_b':''} for _ in range(5)])
        return config
    matches = [t for t in data['ties'] if country in (country_name(t['a']), country_name(t['b']))]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous tie for ' + country)
    tie = matches[0]
    side = int(country_name(tie['b']) == country)
    config['country_b'] = display_country(tie['a'] if side else tie['b'])
    config['score'] = f"{tie['score'][side]}-{tie['score'][1-side]}"
    for match in tie['matches']:
        values = ['NOT PLAYED', 'NOT PLAYED']
        if match:
            if set_scores:
                values = []
                for games in match:
                    values.append('   '.join(f'[{v}]' if i == 2 and max(match[0][i], match[1][i]) >= 10 else str(v)
                                             for i, v in enumerate(games)))
            else:
                a_wins=sum(a>b for a,b in zip(*match))==2
                values=['W','L'] if a_wins else ['L','W']
        config['rows'].append(dict(value_a=values[side], value_b=values[1-side]))
    return config


def has_results(config):
    return bool(str(config.get('country_b', '')).strip() or str(config.get('score', '')).strip()
                or any(str(row.get(k, '')).strip() for row in config.get('rows', [])
                       for k in ('value_a', 'value_b')))


def run(args):
    data = json.loads(args.source.read_text(encoding='utf-8'))
    validate_results(data)
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output/'sources.json', data)
    snapshot = request_json(args.server+'/api/templates')
    if snapshot.get('warnings'):
        raise ValueError('Library warnings; no updates made')
    atomic_json(args.output/'library-before.json', snapshot)
    plan = []
    for country in COUNTRIES:
        label = display_country(country)
        target = dict(template='t7', country=label, player=label+' - Qualifier Rounds')
        entries = [x for x in snapshot['templates'] if identity(x) == identity(target)]
        if len(entries) != 1:
            raise ValueError('Expected one existing country preset: '+label)
        item = entries[0]
        config = copy.deepcopy(item['config'])
        populated = config_for_country(data, country)
        fields = ('country_a', 'country_b', 'score', 'rows')
        config.update({key:populated[key] for key in fields})
        status = 'already-filled' if all(config[k] == item['config'].get(k) for k in fields) else (
            'preserve-operator-results' if has_results(item['config']) else 'ready')
        if args.convert_set_scores and status=='preserve-operator-results':
            legacy=config_for_country(data,country,set_scores=True)
            if all(legacy[k]==item['config'].get(k) for k in fields):
                status='ready'
        plan.append(dict(id=item['id'], country=label, edit_revision=item['edit_revision'],
                         config=config, status=status))
        core.render_t7(config).save(args.output/(label.replace(' ', '_')+'.png'))
    atomic_json(args.output/'plan.json', plan)
    if not args.publish:
        print('Review only. No templates changed: '+str(args.output))
        return
    password = os.environ.get('SCOREBOARD_EDITOR_PASSWORD') or getpass.getpass('Host editor password: ')
    results = []
    for entry in plan:
        if entry['status'] == 'ready':
            # The server rejects stale revisions and backs up the existing preset.
            saved = request_json(args.server+'/api/templates/update', dict(id=entry['id'],
                edit_revision=entry['edit_revision'], config=entry['config'],
                username=args.username, password=password))['item']
            if saved['config'] != entry['config']:
                raise ValueError('Saved config differs from reviewed config')
        results.append(dict(id=entry['id'], country=entry['country'], status=entry['status']))
        atomic_json(args.output/'results.json', results)
        print(entry['country']+': '+entry['status'], flush=True)
    atomic_json(args.output/'library-after.json', request_json(args.server+'/api/templates'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('davis_2026_round1_results.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--server', default='http://127.0.0.1:8080')
    parser.add_argument('--username', default='veto')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--convert-set-scores',action='store_true',help='Convert only unchanged imported set-score results to W/L')
    run(parser.parse_args())
