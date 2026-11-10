"""Shareable weekly category chart and complete category/title allocation CSV."""
from pathlib import Path
import json,urllib.request
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'output/exports/category_comparison_20261103_20261109';OUT.mkdir(parents=True,exist_ok=True)
body=dict(start='2026-11-03',end='2026-11-09',filters={},timeStart='00:00',timeEnd='23:59')
def request(path):return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8766'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=120)
d=json.load(request('/api/category-insights'));(OUT/'analysis.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
(OUT/'categories_and_all_titles.csv').write_bytes(request('/api/category-insights-export').read())
focused={**body,'category_asset_host':'tennis-vod.akamaized.net','category_asset_key':'695mjnfl'}
req=urllib.request.Request('http://127.0.0.1:8766/api/category-insights',data=json.dumps(focused).encode(),headers={'Content-Type':'application/json'})
asset=json.load(urllib.request.urlopen(req,timeout=120))['asset_focus'];(OUT/'example_asset_split.json').write_text(json.dumps(asset,indent=2),encoding='utf-8')
fig,axes=plt.subplots(2,1,figsize=(14,9),constrained_layout=True)
fig.suptitle('Logged category / placement trends | 3-9 November 2026 IST',fontsize=17,fontweight='bold')
for ax,kind,title in [(axes[0],'Content-category label','Largest named content-category labels'),(axes[1],'Placement / collection / campaign label','Largest placement / collection / campaign tags')]:
    keys=[r['category_key'] for r in d['categories'] if r['tag_type']==kind and r['hours']>0][:5]
    for key in keys:
        s=next(s for s in d['series'] if s['key']==key)
        ax.plot(range(len(s['points'])),[p['value'] for p in s['points']],marker='o',linewidth=2,label=s['label'])
    ax.set(title=title,ylabel='Estimated watch hours / day',xticks=range(7),xticklabels=[f'{i} Nov' for i in range(3,10)],ylim=(0,None));ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(fontsize=9,ncol=2)
unknown=next(r['hours'] for r in d['categories'] if r['category_key']=='unknown')
fig.supxlabel(f'Each source row contributes to one tag. Untagged: {unknown/d["summary"]["current"]*100:.2f}% of selected hours. Tags are not a verified genre catalogue.',fontsize=10)
fig.savefig(OUT/'category_trends.png',dpi=150,facecolor='white');fig.savefig(OUT/'category_trends.svg',facecolor='white');plt.close(fig)
print(json.dumps({'folder':str(OUT),'top_categories':d['categories'][:5],'example_asset_split':asset},default=str))
