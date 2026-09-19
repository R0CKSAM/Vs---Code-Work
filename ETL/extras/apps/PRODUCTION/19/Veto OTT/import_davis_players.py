"""Review-first Players Stats importer. Never controls SDI or overwrites presets."""
import argparse
import base64
import copy
import csv
import html
from html.parser import HTMLParser
import json
import os
import re
from pathlib import Path
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import uuid

import scoreboard_app as core

ROOT = Path(__file__).resolve().parent
SOURCE = 'https://www.daviscup.com/en/draws-results/2026/qualifiers?tab=round-2'
COUNTRIES = ('Austria','Belgium','Canada','Chile','Croatia','Czechia','Ecuador',
             'France','Germany','Great Britain','India','South Korea','Spain','United States')


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if c.isalnum())


def country_name(value):
    aliases = {'usa':'United States','us':'United States','unitedstatesofamerica':'United States',
               'korea':'South Korea','korearep':'South Korea','republicofkorea':'South Korea',
               'kor':'South Korea','uk':'Great Britain','unitedkingdom':'Great Britain',
               'czechrepublic':'Czechia'}
    return aliases.get(key(value),next((c for c in COUNTRIES if key(c)==key(value)),str(value).strip()))


def atomic_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name('.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def roster(path):
    players, captains, seen = [], [], set()
    with path.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            row['country'] = country_name(row['country'])
            if row['country'] not in COUNTRIES or not row['name'].strip():
                raise ValueError('Invalid country/name in roster')
            if row['role']=='captain':
                captains.append(row); continue
            if row['role']!='player':
                raise ValueError('Role must explicitly be player or captain')
            identifier = str(uuid.UUID(row['profile_id']))
            if identifier in seen:
                raise ValueError('Duplicate player profile: '+identifier)
            seen.add(identifier)
            row.update(profile_id=identifier,profile_url='https://www.daviscup.com/en/players/'+identifier)
            players.append(row)
    return players,captains


class ProfileHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.h1=False; self.names=[]; self.tokens=[]; self.images=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag=='h1': self.h1=True
        if tag=='img': self.images.append(dict(attrs))
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='h1': self.h1=False
    def handle_data(self,data):
        if self.skip: return
        text=' '.join(data.split())
        if text:
            self.tokens.append(text)
            if self.h1: self.names.append(text)


def parse_profile(document, expected_name):
    parser=ProfileHTML(); parser.feed(document)
    name=' '.join(parser.names)
    if key(name)!=key(expected_name):
        raise ValueError('Profile name mismatch or page unavailable')
    result={'player_name':name,'age':'','headshot_url':''}
    # Deliberately do not infer Davis Cup W/L from rankings or other numbers.
    for i,label in enumerate(parser.tokens[:-1]):
        value=parser.tokens[i+1]
        if label=='Age' and value.isdigit() and 12<=int(value)<=80:
            result['age']=value; break
    for image in parser.images:
        if key(image.get('alt',''))==key('Headshot of '+name):
            url=image.get('src','')
            parsed=urlparse(url)
            if parsed.path=='/_next/image': url=parse_qs(parsed.query).get('url',[''])[0]
            if urlparse(url).scheme=='https': result['headshot_url']=url
    return result


def request_json(url, payload=None):
    data=None if payload is None else json.dumps(payload).encode('utf-8')
    request=Request(url,data=data,headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response:
        return json.load(response)


def existing_matches(items, player):
    return [item['id'] for item in items if item.get('template')=='t6'
            and key(item.get('player'))==key(player['name'])
            and country_name(item.get('country'))==player['country']]


def scraper_rows(path):
    """Read the operator's Selenium export without broadening the nominated roster."""
    if path is None:
        return {}
    result={}
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'COUNTRY','NAME','AGE','TOTAL W/L','DEBUT YEAR','FAVOURATE HAND'} <= set(reader.fieldnames or []):
            raise ValueError('Scraper CSV headers do not match daviscup_scraper.py output')
        for row in reader:
            identity=(country_name(row['COUNTRY']),key(row['NAME']))
            if identity[0] not in COUNTRIES or not identity[1]:
                continue
            # Duplicate identities require review even when values happen to agree.
            result.setdefault(identity,[]).append(row)
    return result


def scraper_values(rows):
    if len(rows)!=1:
        return {},['Ambiguous duplicate scraper rows']
    row=rows[0]; values={}; issues=[]
    rules={
        'age':('AGE',lambda v:v.isascii() and v.isdigit() and 12<=int(v)<=80),
        'total_wl':('TOTAL W/L',lambda v:bool(re.fullmatch(r'[0-9]{1,3}\s*/\s*[0-9]{1,3}',v))),
        'debut_year':('DEBUT YEAR',lambda v:bool(re.fullmatch(r'[0-9]{4}',v)) and 1900<=int(v)<=time.localtime().tm_year),
        'favourite_hand':('FAVOURATE HAND',lambda v:bool(re.fullmatch(
            r'(?:Right|Left|Ambidextrous)(?:[- ]Handed)?(?:\s*\((?:(?:Double|Single|Two|One)[- ]Handed (?:Backhand|Forehand)|None|Both)\))?',v,re.I))),
    }
    for field,(column,valid) in rules.items():
        value=' '.join((row.get(column) or '').split())
        if value and valid(value): values[field]=value
        elif value: issues.append('Review invalid '+column+': '+value)
    return values,issues


def prepare(args):
    players,captains=roster(args.roster)
    scraper_path=getattr(args,'scraper_csv',None)
    scraped=scraper_rows(scraper_path)
    run=args.output/('review-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run.mkdir(parents=True); cache=args.output/'cache'; cache.mkdir(exist_ok=True)
    try:
        snapshot=request_json(args.server+'/api/templates')
        if snapshot.get('warnings'): raise ValueError('Hosted library has unreadable records')
        items=snapshot['templates']; library_error=''
    except Exception as exc:
        items=[]; library_error=str(exc)
    rows=[]; blocked=False
    for player in players:
        identifier=player['profile_id']; cached=cache/(identifier+'.json')
        record=None; error='Not fetched (offline mode)' if args.offline else ''
        try:
            local=args.profile_dir/(identifier+'.html') if args.profile_dir else None
            if local and local.is_file():
                record={'html':local.read_text(encoding='utf-8-sig'),'fetched_at':time.time(),'origin':'operator-supplied HTML'}
            elif cached.exists():
                candidate=json.loads(cached.read_text(encoding='utf-8'))
                if time.time()-candidate['fetched_at']<86400: record=candidate
            if record is None and not args.offline and not blocked:
                try:
                    request=Request(player['profile_url'],headers={'User-Agent':'Veto-Scoreboard-Importer/1.0'})
                    with urlopen(request,timeout=20) as response:
                        data=response.read(5*1024*1024+1)
                        if len(data)>5*1024*1024: raise ValueError('Profile exceeds size limit')
                        document=data.decode('utf-8')
                    parse_profile(document,player['name'])
                    record={'html':document,'fetched_at':time.time(),'origin':player['profile_url']}
                    atomic_json(cached,record)
                except HTTPError as exc:
                    if exc.code in (401,403,429): blocked=True
                    raise
                finally:
                    time.sleep(1)
            if record:
                profile=parse_profile(record['html'],player['name']); error=''
            else:
                profile={}
                if blocked: error='Profile fetching paused after access/rate-limit refusal'
        except Exception as exc:
            profile={}; error=str(exc)
        config=copy.deepcopy(core.DEF_T6)
        config.update(player_name=profile.get('player_name',player['name']),country=player['country'],age=profile.get('age',''))
        csv_rows=scraped.get((player['country'],key(player['name'])),[])
        csv_values,issues=scraper_values(csv_rows) if csv_rows else ({},[])
        for field,value in csv_values.items():
            if config.get(field) and config[field]!=value:
                issues.append('Conflicting '+field+' between profile and CSV; left blank')
                config[field]=''
            else:
                config[field]=value
        sources={'player_name':record['origin'] if profile else 'User-supplied roster',
                 'country':'User-supplied roster (canonicalized)',
                 'age':record['origin'] if profile.get('age') else ''}
        for field in csv_values:
            sources[field]=str(scraper_path.resolve()) if config[field] else ''
        row={**player,'approved':False,'config':config,'image_file':'',
             'scraper_rows_matched':len(csv_rows),'review_issues':issues,
             'profile_verified':bool(profile),
             'profile_status':error or 'Verified name; available fields extracted',
             'profile_fetched_at':record['fetched_at'] if record else None,
             'headshot_url':profile.get('headshot_url',''),
             'existing_ids':existing_matches(items,player) if not library_error else None,
             'missing_fields':[f for f in ('age','total_wl','debut_year','favourite_hand','player_path') if not config[f]],
             'field_sources':sources}
        if csv_rows:
            row['profile_status']='Scraper CSV matched by country/name; values require review. '+'; '.join(issues)
        rows.append(row)
        image=core.render_t6(config); image.thumbnail((640,360))
        image.save(run/(identifier+'.png'))
    report={'schema':1,'roster_source':'User-supplied roster; live nominations not independently confirmed',
            'reference_url':SOURCE,'captains_excluded':captains,'library_error':library_error,
            'created_at':time.time(),'players':rows}
    atomic_json(run/'review.json',report)
    with (run/'review.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(['Country','Player','Age','Total W/L','Debut Year','Favourite Hand','Missing fields','Existing IDs','Profile status','Source','Review issues'])
        for row in rows: writer.writerow([row['country'],row['name'],row['config']['age'],row['config']['total_wl'],row['config']['debut_year'],row['config']['favourite_hand'],', '.join(row['missing_fields']),row['existing_ids'],row['profile_status'],json.dumps(row['field_sources']),'; '.join(row['review_issues'])])
    cards=''.join('<article><h2>'+html.escape(row['country']+' / '+row['name'])+'</h2><img width="640" height="360" src="'+row['profile_id']+'.png"><p>Missing: '+html.escape(', '.join(row['missing_fields']))+'</p><p>'+html.escape(row['profile_status'])+'</p></article>' for row in rows)
    page='<!doctype html><meta charset="utf-8"><title>Players Stats import review</title><style>body{font:14px Arial;margin:20px;background:#edf2f4;color:#15252d}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:16px}article{min-width:0;background:white;padding:12px}h2{font-size:16px}img{max-width:100%;height:auto}p{overflow-wrap:anywhere}</style><h1>Players Stats - Review Only</h1><p>'+str(len(rows))+' players; captains excluded. Nothing published. Unverified values remain blank. '+html.escape(library_error)+'</p><main>'+cards+'</main>'
    (run/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'review':str(run),'players':len(rows),'countries':len({p['country'] for p in players}),
                      'profiles_verified':sum(p['profile_verified'] for p in rows),
                      'scraper_matches':sum(p['scraper_rows_matched']==1 for p in rows),
                      'existing_matches':sum(bool(p['existing_ids']) for p in rows),'library_error':library_error},indent=2))


def publish(args):
    report=json.loads(args.publish.read_text(encoding='utf-8'))
    results=[]
    for row in report['players']:
        if row.get('approved') is not True or row.get('role')!='player': continue
        config=core.normalise_project_configs({'t6':row['config']})['t6']
        config['country']=country_name(config['country'])
        config['player_path']=''
        if not config['player_name'].strip() or config['country'] not in COUNTRIES:
            raise ValueError('Invalid reviewed player/country')
        snapshot=request_json(args.server+'/api/templates')
        if snapshot.get('warnings'): raise ValueError('Hosted library needs attention before publishing')
        matches=existing_matches(snapshot['templates'],{'name':config['player_name'],'country':config['country']})
        if matches:
            results.append({'profile_id':row['profile_id'],'status':'existing - untouched','ids':matches})
        else:
            if row.get('image_file'):
                path=Path(row['image_file'])
                if not path.is_absolute(): path=args.publish.parent/path
                if path.stat().st_size>10*1024*1024: raise ValueError('Player image exceeds 10 MB')
                with core.Image.open(path) as image:
                    import io
                    output=io.BytesIO(); image.convert('RGBA').save(output,format='PNG')
                if output.tell()>20*1024*1024: raise ValueError('Expanded PNG exceeds upload limit')
                uploaded=request_json(args.server+'/api/upload',{'name':path.name,'data':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')})
                config['player_path']=uploaded['path']
            result=request_json(args.server+'/api/templates/save',{'template':'t6','player':config['player_name'],'country':config['country'],'config':config})
            results.append({'profile_id':row['profile_id'],'result':result})
        atomic_json(args.publish.with_name('publish-results.json'),results)
    print(json.dumps({'reviewed_players_processed':len(results),'results':str(args.publish.with_name('publish-results.json'))},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roster',type=Path,default=ROOT/'davis_cup_2026_round2.csv')
    parser.add_argument('--output',type=Path,default=ROOT/'data/davis_import')
    parser.add_argument('--server',default='http://127.0.0.1:8080')
    parser.add_argument('--offline',action='store_true',help='Use fresh cache/local HTML only; no profile requests')
    parser.add_argument('--profile-dir',type=Path,help='Operator-supplied profile HTML files named PROFILE_UUID.html')
    parser.add_argument('--scraper-csv',type=Path,help='CSV exported by daviscup_scraper.py; review only, matched to nominated roster')
    parser.add_argument('--publish',type=Path,help='Publish only approved:true player entries from a reviewed JSON')
    args=parser.parse_args(); args.server=args.server.rstrip('/')
    if urlparse(args.server).scheme not in ('http','https'): parser.error('Server must use HTTP(S)')
    publish(args) if args.publish else prepare(args)


if __name__=='__main__':
    main()
