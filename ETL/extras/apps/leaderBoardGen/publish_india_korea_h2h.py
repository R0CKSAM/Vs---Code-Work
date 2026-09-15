"""Create-only India/Korea Head2Head drafts from saved player presets."""
import argparse
import copy
from pathlib import Path

import scoreboard_app as core
from import_davis_players import atomic_json, request_json, country_name
from publish_davis_presets import identity


def build_pairs(library):
    teams=[]
    for country in ('India','South Korea'):
        players=[x for x in library if x['template']=='t6' and country_name(x['country'])==country
                 and x['player']!='Original']
        if len(players)!=5 or len({x['player'].casefold() for x in players})!=5:
            raise ValueError('Expected five distinct saved players for '+country)
        teams.append(sorted(players,key=lambda x:x['player']))
    pairs=[]
    for a in teams[0]:
        for b in teams[1]:
            cfg=copy.deepcopy(core.DEF_T9)
            cfg.update(player_a=a['player'],player_b=b['player'],country_a='INDIA',country_b='KOREA',
                       photo_a=a['config'].get('player_path',''),photo_b=b['config'].get('player_path',''),meeting='')
            for row in cfg['rows']:
                field={'Age':'age','Davis Cup W-L':'total_wl'}.get(row['label'])
                row['value_a']=a['config'].get(field,'') if field else ''
                row['value_b']=b['config'].get(field,'') if field else ''
            pairs.append(dict(template='t9',player=a['player']+' vs '+b['player'],country='INDIA',config=cfg,
                              source_presets=[a['id'],b['id']],unverified=['ATP Ranking','2026 W-L','Career High','Head-to-Head','meeting']))
    return pairs


def run(args):
    snapshot=request_json(args.server+'/api/templates')
    if snapshot.get('warnings'):
        raise ValueError('Resolve library warnings before publishing')
    pairs=build_pairs(snapshot['templates'])
    args.output.mkdir(parents=True,exist_ok=False)
    atomic_json(args.output/'library-before.json',snapshot)
    atomic_json(args.output/'plan.json',pairs)
    results=[]
    for index,pair in enumerate(pairs):
        core.render_t9(pair['config']).save(args.output/f'{index+1:02d}.png')
        if not args.publish:
            continue
        existing=next((x for x in snapshot['templates'] if identity(x)==identity(pair)),None)
        if existing:
            result=dict(player=pair['player'],status='preserved',id=existing['id'])
        else:
            response=request_json(args.server+'/api/templates/save',{k:pair[k] for k in ('template','player','country','config')})
            saved=response.get('item') or response['existing']
            result=dict(player=pair['player'],status='created' if response.get('saved') else 'preserved',id=saved['id'])
        results.append(result)
        atomic_json(args.output/'results.json',results)
        print(result['player']+': '+result['status'],flush=True)
    after=request_json(args.server+'/api/templates')
    atomic_json(args.output/'library-after.json',after)
    current={x['id']:x for x in after['templates']}
    for old in snapshot['templates']:
        if current.get(old['id'])!=old:
            raise ValueError('Concurrent library change detected; inspect snapshots: '+old['player'])
    print('Pairings: '+str(len(pairs))+'; unverified ATP fields left blank. No live commands sent.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--server',default='http://127.0.0.1:8080')
    parser.add_argument('--publish',action='store_true')
    run(parser.parse_args())
