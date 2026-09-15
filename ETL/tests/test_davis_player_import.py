import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_scoreboard_app import MODULE_PATH,scoreboard

SPEC=importlib.util.spec_from_file_location('davis_import',MODULE_PATH.with_name('import_davis_players.py'))
sys.modules.setdefault('scoreboard_app',scoreboard)
importer=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(importer)


def test_roster_captains_and_aliases():
    players,captains=importer.roster(MODULE_PATH.with_name('davis_cup_2026_round2.csv'))
    assert len(players)==63 and len(captains)==14
    assert len({p['country'] for p in players})==14
    assert 'Rohit Rajpal' not in [p['name'] for p in players]
    assert importer.country_name(' INDIA ')=='India'
    assert importer.country_name('Korea, Rep.')=='South Korea'
    assert importer.country_name('USA')=='United States'


def test_profile_values_require_matching_name_and_age_label():
    source='<script>Age 99</script><h1>Dhakshineswar Suresh</h1><div>Age</div><span>26</span><div>Singles Ranking</div><span>368</span>'
    result=importer.parse_profile(source,'Dhakshineswar Suresh')
    assert result['age']=='26'
    assert 'total_wl' not in result and 'debut_year' not in result
    assert importer.parse_profile('<h1>Player</h1><p>Ranking</p><p>26</p>','Player')['age']==''
    with pytest.raises(ValueError,match='mismatch'):
        importer.parse_profile(source,'Someone Else')


def test_preview_offline_never_writes_to_server(tmp_path,monkeypatch):
    roster=tmp_path/'roster.csv'
    roster.write_text('country,role,name,profile_id\nIndia,player,Player,00000000-0000-0000-0000-000000000001\nIndia,captain,Captain,\n')
    calls=[]
    def request(url,payload=None):
        calls.append((url,payload));return {'templates':[],'warnings':[]}
    monkeypatch.setattr(importer,'request_json',request)
    args=SimpleNamespace(roster=roster,output=tmp_path/'out',server='http://host',offline=True,profile_dir=None)
    importer.prepare(args)
    review=next(args.output.glob('review-*/review.json'))
    data=json.loads(review.read_text())
    assert len(data['players'])==1 and not data['players'][0]['approved']
    assert data['players'][0]['config']['age']==''
    assert all(payload is None for _,payload in calls)
    assert review.with_name('index.html').exists()


def test_publish_only_approved_and_skip_country_alias_duplicates(tmp_path,monkeypatch):
    def row(name,approved):
        return {'role':'player','profile_id':name,'approved':approved,'config':{
            **importer.core.DEF_T6,'player_name':name,'country':'South Korea'},'image_file':''}
    path=tmp_path/'review.json'
    path.write_text(json.dumps({'players':[row('Existing',True),row('New',True),row('Not Reviewed',False)]}))
    calls=[]
    def request(url,payload=None):
        calls.append((url,payload))
        if payload is None:return {'templates':[{'id':'one','template':'t6','player':'Existing','country':'Korea, Rep.'}],'warnings':[]}
        return {'saved':True,'item':payload}
    monkeypatch.setattr(importer,'request_json',request)
    importer.publish(SimpleNamespace(publish=path,server='http://host'))
    writes=[payload for _,payload in calls if payload]
    assert len(writes)==1 and writes[0]['player']=='New'
    assert all('/api/live' not in url for url,_ in calls)
    assert path.with_name('publish-results.json').exists()


def test_scraper_csv_validation_and_duplicates(tmp_path):
    path=tmp_path/'scraped.csv'
    path.write_text('COUNTRY,NAME,AGE,TOTAL W/L,DEBUT YEAR,FAVOURATE HAND\n'
                    'Korea,Player,28,15/11,2017,Right (Double Handed Backhand)\n',encoding='utf-8')
    rows=importer.scraper_rows(path)[('South Korea','player')]
    values,issues=importer.scraper_values(rows)
    assert values=={'age':'28','total_wl':'15/11','debut_year':'2017',
                    'favourite_hand':'Right (Double Handed Backhand)'}
    assert not issues
    assert importer.scraper_values(rows+rows)[0]=={}
    rows[0].update({'AGE':'28 Singles Ranking 30','TOTAL W/L':'300','DEBUT YEAR':'9999','FAVOURATE HAND':'Age 28'})
    values,issues=importer.scraper_values(rows)
    assert not values and len(issues)==4


def test_scraper_preview_uses_roster_only(tmp_path,monkeypatch):
    roster=tmp_path/'roster.csv'
    roster.write_text('country,role,name,profile_id\nIndia,player,Player,00000000-0000-0000-0000-000000000001\nIndia,captain,Captain,\n')
    source=tmp_path/'source.csv'
    source.write_text('COUNTRY,NAME,AGE,TOTAL W/L,DEBUT YEAR,FAVOURATE HAND\n'
                      'India,Player,26,5/3,2017,Right\n'
                      'India,Captain,45,10/5,2000,Left\n'
                      'India,Unnominated,22,1/0,2025,Left\n')
    monkeypatch.setattr(importer,'request_json',lambda url:{'templates':[]})
    args=SimpleNamespace(roster=roster,output=tmp_path/'out',server='http://host',
                         offline=True,profile_dir=None,scraper_csv=source)
    importer.prepare(args)
    report=json.loads(next(args.output.glob('review-*/review.json')).read_text())
    assert len(report['players'])==1
    player=report['players'][0]
    assert player['config']['total_wl']=='5/3' and player['config']['age']=='26'
    assert not player['approved'] and not player['profile_verified']
    assert player['field_sources']['total_wl']==str(source.resolve())
