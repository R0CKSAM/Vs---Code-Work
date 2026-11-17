"""Build Veto's editable sponsor presentation from aggregate-only analysis files."""
from pathlib import Path
import json, csv
from urllib.parse import unquote
from datetime import datetime
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.chart.data import CategoryChartData

ROOT=Path(__file__).resolve().parent
A=json.loads((ROOT/'analysis.json').read_text())
Q=json.loads((ROOT/'quality_details.json').read_text())
M=json.loads((ROOT/'active_metrics.json').read_text())
O=A['overall'][0]; TOTAL=O['requests']; ACTIVE=Q['identity_quality'][0]['positive_ips']
BG='101923'; PANEL='1A2836'; WHITE='F4F7FA'; MUTED='A6B8C9'; ORANGE='FF8150'; LIME='C5F279'; BLUE='71C9E8'; LINE='344657'
R=Presentation(); R.slide_width=Inches(13.333); R.slide_height=Inches(7.5)
R.core_properties.title='Veto Sports | Measured Scale. Sponsor Opportunity.'
R.core_properties.subject='Sports streaming portfolio and proposed sponsorship partnerships'
R.core_properties.author='Veto Streaming | Stakeholder presentation'
R.core_properties.keywords='sports, sponsors, Veto, portfolio, streaming'

def rgb(c): return RGBColor.from_string(c)
def box(s,x,y,w,h,fill=PANEL,radius=False):
 sh=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
 sh.fill.solid();sh.fill.fore_color.rgb=rgb(fill);sh.line.fill.background()
 if radius:
  try: sh.adjustments[0]=.12
  except Exception: pass
 return sh
def text(s,x,y,w,h,t,size=20,color=WHITE,bold=False):
 sh=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=sh.text_frame;tf.word_wrap=True
 tf.margin_left=tf.margin_right=0;tf.margin_top=tf.margin_bottom=0
 for i,line in enumerate(t.split('\n')):
  p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line;p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color);p.space_after=Pt(7)
 return sh
def slide(k,title,sub='',foot='Source: supplied sports Parquet | 18 Sep–14 Nov 2026 | IST',notes=''):
 s=R.slides.add_slide(R.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=rgb(BG)
 box(s,.45,.42,.09,.2,ORANGE);text(s,.68,.37,10,.25,'VETO  /  SPORTS PARTNERSHIPS',11,MUTED,True)
 text(s,11.25,.37,1.4,.25,k.upper(),10,LIME,True)
 text(s,.68,.95,12,1.5 if '\n' in title else 1,title,31,WHITE,True)
 if sub:text(s,.7,1.95,11.9,.55,sub,14,MUTED)
 box(s,.7,6.96,11.95,.012,LINE);text(s,.7,7.08,11.2,.2,foot,9,MUTED);text(s,12.1,7.05,.55,.25,f'{len(R.slides):02}',11,MUTED)
 s.notes_slide.notes_text_frame.text=notes or sub
 return s
def num(n):
 return f'{n/1e6:.2f}M' if n>=1e6 else f'{n/1000:.1f}K' if n>=1000 else str(n)
def card(s,x,y,w,value,label,detail='',accent=LIME):
 box(s,x,y,w,2.05,PANEL,True);text(s,x+.22,y+.18,w-.4,.65,value,38,accent,True);text(s,x+.22,y+.94,w-.4,.45,label,17,WHITE,True)
 if detail:text(s,x+.22,y+1.45,w-.4,.45,detail,11,MUTED)
def bars(s,labels,vals,x,y,w,h,color=ORANGE,percent=False):
 maxv=max(vals);rh=h/len(vals)
 for i,(lab,v) in enumerate(zip(labels,vals)):
  yy=y+i*rh;text(s,x,yy,2.85,.32,lab,13,MUTED)
  box(s,x+3,yy+.025,max(.025,(w-4.25)*v/maxv),.2,color)
  text(s,x+w-1.15,yy-.025,1.15,.35,f'{v:.1f}%' if percent else num(v),15,WHITE,True)
def note(s,t):text(s,.72,6.35,11.8,.45,t,11,MUTED)

# 01 / Cover
s=slide('Portfolio','Sport creates the moment.\nVeto brings the streaming scale.',notes='Sponsor-facing retrospective based only on the supplied file. The six property names are source labels, not proof of event ownership, rights or organiser status. No claim is made that Veto organised these tournaments. The pitch concerns the observed streaming portfolio and proposed commercial activations. All future inventory is subject to approval and rights clearance.')
text(s,.73,2.65,7.7,.75,'A multi-sport partnership platform',24,LIME,True)
text(s,.73,3.55,7.3,1.5,'Six recorded properties. Four sport categories.\nOne measurable portfolio for the next sponsor conversation.',22,WHITE)
text(s,.73,5.6,7.3,.65,'PORTFOLIO REVIEW  /  18 SEP–14 NOV 2026\nPrepared for stakeholder and sponsor discussions · 17 Nov 2026',12,MUTED)
box(s,9.1,2.65,3.5,3.6,PANEL,True);text(s,9.35,3.05,3,.85,'3.42M',48,ORANGE,True);text(s,9.35,4.05,2.95,1.05,'Distinct client IPs\nwith recorded TS requests',20,WHITE,True);text(s,9.35,5.5,2.95,.45,'Delivery footprint · not verified people',11,MUTED)

# 02 / KPI summary
s=slide('The case','A portfolio with measurable delivery at scale','A conservative headline: only client IPs attached to positive TS request counts.',notes='3,422,658 distinct trimmed nonblank cli_ip values on rows where raw_ts_requests > 0. Total raw TS requests = 1,204,891,915. Six distinct Event Name labels. 31 distinct ist_date values within an interval of 58 calendar days; unrepresented dates are not inferred to be inactive. Counts are deduplicated across the complete file, not summed across events. IPs are not people or households; requests are transport segments, not ad impressions or viewing minutes.')
card(s,.72,2.8,3.83,'3.42M','Distinct delivery client IPs','Positive-request rows only')
card(s,4.75,2.8,3.83,'1.20B','Raw TS requests','Recorded delivery volume',ORANGE)
card(s,8.78,2.8,3.83,'6','Sports properties','Across 31 recorded dates',BLUE)
text(s,.78,5.32,11.7,.65,'The pitch: combine cricket-led scale with a broader sports context.',25,WHITE,True)
note(s,'Client IPs are a network identifier proxy. Segment requests are not ad impressions, concurrent users or watch time.')

# 03 / Portfolio
lookup={r['label'] if 'label' in r else r['event_label']:r['active_ips'] for r in Q['ip_event_positive']}
events=sorted(A['events'],key=lambda e:lookup[e['event_label']],reverse=True)
s=slide('Breadth','Six properties. A clear scale anchor.','Distinct client IPs with recorded TS requests, deduplicated within each property.',notes='Bars use positive raw_ts_requests only. Event reach overlaps: never sum these client-IP counts into portfolio reach. Preserve source event labels; sport classification for the narrative: ODI and T20 = cricket; SAFF = football; Davis Cup/BJKC = tennis; Weightlifting = weightlifting. Source fixture labels are not validated match schedules.')
bars(s,[e['event_label'] for e in events],[lookup[e['event_label']] for e in events],.78,2.85,11.65,3.1)
note(s,'Property totals overlap. Portfolio client IPs are independently deduplicated. Event labels follow the source file.')

# 04 / cricket
cricket=sum(e['requests'] for e in events if e['event_label'] in ['ODI Tri Series','Pak-Sl T20 Series'])
s=slide('Cricket','Cricket is the portfolio’s delivery engine','Use the largest observed properties as the anchor for a proposed sponsor package.',notes=f'ODI Tri Series: 2,627,242 positive-request client IPs and 985,460,604 TS requests. Pak-Sl T20 Series: 314,338 positive-request client IPs and 115,772,301 requests. Combined cricket request share is {cricket/TOTAL:.6%}. Do not add the IP counts: overlap exists. This is a proposed positioning, not proof of sponsorship rights. Source Match Name has Pak-Eng and Eng-Pak labels; do not call the 11 labels 11 unique fixtures.')
card(s,.73,2.75,3.8,'2.63M','ODI Tri Series','Distinct delivery client IPs')
card(s,4.77,2.75,3.8,'314.3K','Pak–SL T20 Series','Distinct delivery client IPs',BLUE)
card(s,8.81,2.75,3.8,f'{cricket/TOTAL:.1%}','Of raw TS requests','Cricket properties combined',ORANGE)
text(s,.8,5.32,11.5,.75,'Proposed platform: an anchor partnership with recurring match-window visibility.',23,WHITE,True)
note(s,'No sponsorship inventory, audience demographics or media-value estimate is established by this file.')

# 05 / multisport
s=slide('Beyond cricket','Build category relevance across more sports','Football and specialist properties create distinct sponsorship contexts.',notes='Positive-request IP counts: SAFF 470,168; Davis Cup 49,927; Weightlifting 46,651; BJKC 18,379. These are overlapping IP proxies rather than unique people. Suggested category fit is a strategic hypothesis, not a finding about age, income, purchase intent or brand affinity. BJKC acronym intentionally retained as supplied.')
spec=[('SAFF Championship','470.2K','Football','Team-led storytelling and community participation'),('Davis Cup','49.9K','Tennis','Performance and precision-led creative'),('Weightlifting','46.7K','Strength sport','Training, preparation and discipline-led creative'),('BJKC 2026','18.4K','Tennis','A distinct property for a focused partnership')]
for i,(name,v,sport,idea) in enumerate(spec):
 x=.73+(i%2)*6.03;y=2.7+(i//2)*1.65
 box(s,x,y,5.8,1.43,PANEL,True);text(s,x+.2,y+.15,3.7,.3,name,20,WHITE,True);text(s,x+4,y+.15,1.55,.4,v,24,LIME,True);text(s,x+.2,y+.61,5.35,.25,sport.upper()+' / DISTINCT DELIVERY CLIENT IPS',10,MUTED);text(s,x+.2,y+.98,5.3,.3,idea,12,MUTED)
note(s,'Brand associations shown are proposed creative directions. Per-property client-IP figures are not additive.')

# 06 / dates native chart
peak=max(M['daily_active'],key=lambda x:x['ips'])
s=slide('Timing','High-attention dates deserve a planned activation','Daily distinct delivery client IPs across the 31 dates represented in the file.',notes=f'Daily maximum {peak["ips"]:,} client IPs on {peak["date_label"]}. This is daily distinct IPs, not peak concurrent viewers. Native editable PowerPoint line chart uses an evenly spaced category axis of represented dates, not a continuous daily calendar. Gaps between dates are explicitly not filled as zero. No claim of complete season coverage.')
data=CategoryChartData();data.categories=[datetime.fromisoformat(d['date_label']).strftime('%d %b') for d in M['daily_active']];data.add_series('Daily distinct delivery client IPs (thousands)',[d['ips']/1000 for d in M['daily_active']])
chart=s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(.72), Inches(2.75), Inches(8.65), Inches(3.3),data).chart
chart.has_legend=False;chart.chart_style=13;chart.has_title=False
chart.chart_area if hasattr(chart,'chart_area') else None
ser=chart.series[0];ser.format.line.color.rgb=rgb(ORANGE);ser.format.line.width=Pt(3)
chart.category_axis.tick_labels.font.size=Pt(9);chart.category_axis.tick_labels.font.color.rgb=rgb(MUTED)
chart.value_axis.tick_labels.font.size=Pt(10);chart.value_axis.tick_labels.font.color.rgb=rgb(MUTED);chart.value_axis.minimum_scale=0
box(s,9.7,2.9,2.85,2.6,PANEL,True);text(s,9.95,3.15,2.4,.65,'756.0K',35,LIME,True);text(s,9.95,4,2.35,1.3,'Highest daily footprint\n31 October 2026',18,WHITE,True)
note(s,'Thousands of client IPs per recorded date; equal spacing between labels. Daily distinct is not concurrent audience.')

# 07 / geography request share
ind=next(r for r in Q['country_reqs'] if r['category']=='IN');states=Q['state_reqs'][:6]
s=slide('Geography','An India-led delivery footprint','India accounts for 98.8% of recorded TS requests. State chart uses share of India requests.',notes='India request share = 1,190,960,079 / 1,204,891,915. Region values decoded from URL escapes for display; underlying data not modified. Country and state are source-provided location labels; no independent location verification. Shares use TS requests, not people. Regional creative and targeting require separately confirmed inventory and consent/policy compliance.')
bars(s,[unquote(e['category']) for e in states],[100*e['requests']/ind['requests'] for e in states],.78,2.85,8.8,3.05,LIME,True)
box(s,10,2.8,2.55,3.05,PANEL,True);text(s,10.22,3.12,2.15,.7,'98.8%',34,ORANGE,True);text(s,10.22,4.05,2.1,1.3,'India share of\nraw TS requests',19,WHITE,True)
note(s,'Geography describes request delivery, not demographic composition or guaranteed targetable inventory.')

# 08 / Device request shares
groups={'Desktop':0,'Mobile + phablet':0,'Smart TV + streaming':0,'Tablet':0,'Other / unclassified':0}
for d in A['devices']:
 key={'desktop':'Desktop','smartphone':'Mobile + phablet','phablet':'Mobile + phablet','smart_tv':'Smart TV + streaming','streaming_device':'Smart TV + streaming','tablet':'Tablet'}.get(d['category'],'Other / unclassified');groups[key]+=d['requests']
s=slide('Screens','Plan creative for the screens in the delivery mix','Share of raw TS requests by source-classified device category.',notes='Device chart uses summed request counts, not distinct device IDs. This avoids misleading additive device reach: the same ID may appear in more than one device classification, and 62.5% of source rows lack a nonblank device ID. Category classification comes from the supplied file and is not independently audited. Smart TV share is not measured co-viewing or household reach. Device targeting feasibility must be confirmed separately.')
bars(s,list(groups),[v/TOTAL*100 for v in groups.values()],.78,2.9,8.7,2.75,BLUE,True)
text(s,9.9,2.85,2.55,.85,'A screen-aware proposal',20,LIME,True);text(s,9.9,3.85,2.5,1.75,'Desktop: clear messaging\nMobile: concise creative\nTV: legible brand assets',17,WHITE)
note(s,'Request mix is not audience share, ad exposure, co-viewing or watch-time share.')

# 09 / proposal architecture
s=slide('Proposal','Three ways to partner with the portfolio','Proposed commercial architecture — scope, availability and pricing to be agreed.',foot='Proposed inventory only | Subject to rights, production approval and technical feasibility',notes='All packages on this slide are proposals and not statements of existing owned inventory, previous sponsorship delivery, exclusivity rights or booked revenue. No rate card, ad logs, rights documents or production plan was supplied. Confirm category exclusivity and rights before a quote. Avoid guaranteeing outcomes based on IP or request counts.')
packs=[('PORTFOLIO PARTNER','Breadth across selected properties',['A consistent campaign narrative','Agreed multi-property placements','Consolidated delivery reporting'],ORANGE),('PROPERTY PARTNER','One focused sports context',['Selected event-window association','Approved contextual creative','Property-level reporting'],LIME),('MOMENT PARTNER','A focused activation window',['Selected dates or segments','Simple, testable call to action','Campaign-specific measurement'],BLUE)]
for i,(name,sub,items,col) in enumerate(packs):
 x=.73+i*4.04;box(s,x,2.75,3.8,3.15,PANEL,True);box(s,x,2.75,3.8,.06,col);text(s,x+.22,3.02,3.35,.55,name,20,col,True);text(s,x+.22,3.73,3.35,.6,sub,17,WHITE,True)
 for j,t in enumerate(items):text(s,x+.22,4.55+j*.36,3.35,.35,'• '+t,12,MUTED)

# 10 / activation
s=slide('Activation','Turn a sports moment into a brand journey','An example activation plan, to be developed with the sponsor.',foot='Illustrative activation plan | Requires rights clearance, production approval and instrumentation',notes='Illustrative concepts only. Teasers, branded segments, scorecards, recaps, polls and QR calls to action are not proven available in the current stream. They must be rights-cleared and instrumented before launch. No assumption of customer conversion, demographic targeting or attribution is supported by the file.')
steps=[('01','BUILD ANTICIPATION','Before the stream','Approved teaser assets\nClear campaign message'),('02','OWN A RELEVANT MOMENT','During the window','Approved branded segment\nContextual call to action'),('03','EXTEND THE CONVERSATION','After the event','Rights-cleared recap\nTracked campaign follow-up')]
for i,(n,head,when,body) in enumerate(steps):
 x=.75+i*4.02;text(s,x,2.75,1,.6,n,37,ORANGE,True);text(s,x,3.6,3.65,.6,head,20,WHITE,True);text(s,x,4.4,3.55,.4,when,15,LIME,True);text(s,x,5.08,3.55,.9,body,16,MUTED)

# 11 / scorecard
s=slide('Accountability','Give sponsors a clear delivery scorecard','Separate what this file proves from the campaign metrics we need to add.',notes='Existing file supports property/date TS counts, client-IP counts, and location/device request mix. It does not include ad serving or render evidence, impressions, clicks, QR scans, sales, concurrent sessions, duration, buffering, ad completion or brand uplift. Require ad-server, player and sponsor analytics integrations to report those metrics. This slide is a proposed measurement design.')
box(s,.73,2.72,5.78,3.3,PANEL,True);box(s,6.76,2.72,5.78,3.3,PANEL,True)
text(s,.98,3,5.25,.4,'AVAILABLE TODAY',18,LIME,True);text(s,.98,3.73,5.1,1.65,'Property and date delivery footprint\nRaw TS request counts\nDevice and geography request mix\nTransparent scope and methodology',18,WHITE)
text(s,7.01,3,5.2,.4,'ADD FOR THE SPONSOR CAMPAIGN',18,ORANGE,True);text(s,7.01,3.73,5.1,1.65,'Verified ad delivery and completion\nTracked clicks or QR responses\nSponsor-owned conversion reporting\nAgreed attribution and success criteria',18,WHITE)
note(s,'Do not substitute TS requests for paid-media impressions or report commercial ROI from delivery logs alone.')

# 12 / close
s=slide('Next move','Let’s build the next sports partnership.','A scoped pilot gives sponsors a clear proposition and gives Veto a measurable case study.',foot='Commercial next steps | No pricing, exclusivity or future audience guarantee implied',notes='CEO-style commercial recommendation: agree category/objective, verify rights and placements, choose property/window, agree measurement and budget, then launch a pilot and review verified campaign results. No contacts, prices, contracted properties or future event dates have been invented. Historical footprint is not a future delivery guarantee.')
for i,(h,b) in enumerate([('Choose the objective','Brand visibility, participation or a tracked response.'),('Choose the scope','One property, one window or a defined portfolio package.'),('Agree the proof','Inventory, creative, budget and reporting before launch.')]):
 y=2.75+i*1.05;text(s,.78,y,.55,.4,f'{i+1:02}',22,ORANGE,True);text(s,1.55,y,4.2,.4,h,22,WHITE,True);text(s,6,y+.02,6.1,.6,b,18,MUTED)
box(s,.74,6.12,11.8,.49,LIME);text(s,.98,6.18,11.2,.3,'NEXT STEP  /  Agree a sponsor brief and rights-cleared pilot scope.',17,BG,True)

# 13 / appendix exact facts
s=slide('Appendix','The property scorecard','Exact source aggregates. Positive-request client IPs are independently deduplicated per property.',notes='Rows and event ranges below are observations in this dataset, not a certified tournament schedule. The sum of per-event requests reconciles to the portfolio total. Per-event client-IP counts overlap and must not be summed. No raw IP address or device ID is included in the deck or companion CSV files.')
cols=[.78,4.12,6.78,9.35];widths=[3.25,2.4,2.4,2.9]
for x,w,t in zip(cols,widths,['PROPERTY','DELIVERY CLIENT IPS','RAW TS REQUESTS','RECORDED DATES']):text(s,x,2.68,w,.35,t,11,LIME,True)
for i,e in enumerate(events):
 y=3.18+i*.43
 if i%2==0:box(s,.73,y-.04,11.85,.42,PANEL)
 vals=[e['event_label'],f"{lookup[e['event_label']]:,}",f"{e['requests']:,}",f"{e['day_count']} dates"]
 for x,w,t in zip(cols,widths,vals):text(s,x,y,w,.32,t,14,WHITE)
text(s,.8,6.03,11.7,.4,'Portfolio total: 3,422,658 delivery client IPs  |  1,204,891,915 raw TS requests',17,ORANGE,True)

# 14 / methods
s=slide('Appendix','Measurement that protects the sponsor story','Definitions, scope and limits for this presentation.',notes='Source: Y:\\Veto Logs Backup\\Chinmoy\\sports_all_dates_12_columns.parquet. 8,152,086 rows, 12 columns, 67 row groups, file size 165,177,544 bytes; last modified 16 November 2026. All 8,152,086 rows are distinct across all 12 fields (no exact duplicates). No negative or null raw_ts_requests. cli_ip is complete and no common placeholder IP values were found. 5,094,230 rows (62.5%) have blank device_id. Only three positive-request rows carry a nonblank device_id, so device identity is not joined to delivery volume for audience claims. 3,950,608 IPs exist across all rows, but headline excludes zero-request-only IPs, yielding 3,422,658. The data spans 58 calendar days with only 31 dates represented; completeness cannot be certified without a source coverage audit. No request duration, HTTP status, player/ad logs, rights or commercial documentation supplied.')
items=[('Scope','18 Sep–14 Nov 2026; 31 represented IST dates; six source event labels.'),('Headline footprint','Distinct trimmed client IPs on rows with raw_ts_requests > 0; not unique people.'),('Delivery volume','Sum of raw_ts_requests; not impressions, concurrent users, views or minutes.'),('Deduplication','Portfolio IPs are deduplicated globally; event and regional counts can overlap.'),('Identity quality','62.5% of rows lack device IDs; device reach is not used as the headline KPI.'),('Commercial scope','Proposals require rights and inventory validation; historical delivery is not a guarantee.')]
for i,(h,b) in enumerate(items):
 y=2.7+i*.55;text(s,.8,y,2.45,.4,h,15,LIME,True);text(s,3.35,y,9.05,.48,b,14,WHITE)
note(s,'Original Parquet remains unchanged. Companion aggregates and speaker notes provide the audit trail.')

target=ROOT/'Veto_Sports_Sponsor_Presentation.pptx';R.save(target)
for key,rows in [('property_scorecard',[{'property':e['event_label'],'distinct_delivery_client_ips':lookup[e['event_label']],'raw_ts_requests':e['requests'],'recorded_dates':e['day_count'],'first_date':e['first_date'],'last_date':e['finish']} for e in events]),('daily_delivery',M['daily_active']),('geography_requests',Q['state_reqs']),('device_request_mix',[{'category':k,'requests':v,'request_share':v/TOTAL} for k,v in groups.items()])]:
 with (ROOT/(key+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
assert sum(e['requests'] for e in events)==TOTAL
assert sum(groups.values())==TOTAL
assert sum(e['requests'] for e in M['daily_active'])==TOTAL
assert len(R.slides)==14
for s in R.slides:
 for sh in s.shapes:
  assert sh.left>=0 and sh.top>=0 and sh.left+sh.width<=R.slide_width+10000 and sh.top+sh.height<=R.slide_height+10000
print(f'Created {target} | {len(R.slides)} slides | totals reconciled | all shapes within canvas')
