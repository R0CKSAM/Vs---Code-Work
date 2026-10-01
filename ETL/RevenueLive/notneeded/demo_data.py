"""Deterministic, explicitly synthetic August data; only for a demo database."""
import calendar
from contextlib import closing
import csv
import datetime as dt
import json
import math
from pathlib import Path
import random
import sqlite3


def generate_rows(channels, year=2026, month=8):
    rng=random.Random(20260828)
    rows=[]
    for day in range(1,calendar.monthrange(year,month)[1]+1):
        date=dt.date(year,month,day)
        for index,(cid,name) in enumerate(channels):
            weekend=1.22 if date.weekday()>=5 else 1
            trend=1+0.25*math.sin(day/4+index/3)+day/170
            views=round((2800+(index+1)*1050)*weekend*trend*rng.uniform(.75,1.25))
            impressions=round(views*rng.uniform(.20,.70))
            ad=round(impressions*rng.uniform(.8,3.8))
            other=(index+1)*25000 if (day+index)%11==0 else 0
            if day==12 and index%5==0:
                views=impressions=ad=other=0
            rows.append((date.isoformat(),cid,views,impressions,ad,other,ad+other,'demo-2026-08'))
    return rows


def seed_demo(data):
    data=Path(data)
    if data.name!='demo_data' and '.test-data' not in data.parts:
        raise ValueError('Demo seed is restricted to demo_data or .test-data folders.')
    marker=data/'DEMO_DATA.json'
    if marker.exists():
        return
    from app import HEADERS
    with closing(sqlite3.connect(data/'revenuelive.db')) as db,db:
        if db.execute('SELECT 1 FROM records LIMIT 1').fetchone():
            raise ValueError('Refusing to add demo data to a populated database.')
        channels=db.execute('SELECT id,name FROM channels ORDER BY name COLLATE NOCASE').fetchall()
        rows=generate_rows(channels)
        if not rows:
            raise ValueError('Register channels before seeding.')
        source=data/'uploads/DEMO_August_2026.csv'
        source.parent.mkdir(exist_ok=True)
        names=dict(channels)
        with source.open('w',newline='',encoding='utf-8-sig') as handle:
            writer=csv.writer(handle);writer.writerow(HEADERS)
            for day,cid,views,impressions,ad,other,total,_ in rows:
                writer.writerow([day,names[cid],views,impressions,f'{ad/100:.2f}',f'{other/100:.2f}',f'{total/100:.2f}'])
        db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',rows)
        uid=db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
        db.execute('INSERT INTO audit(created,user_id,action,detail) VALUES (?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),uid,'demo_seed','Synthetic August 2026; not actual revenue'))
    marker.write_text(json.dumps({'synthetic':True,'start':'2026-08-01','end':'2026-08-31','channels':len(channels),'rows':len(rows)},indent=2))
