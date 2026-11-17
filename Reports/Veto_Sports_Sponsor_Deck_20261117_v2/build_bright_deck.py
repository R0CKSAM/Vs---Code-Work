"""Editable, sponsor-facing Veto portfolio deck. Aggregates only; original source unchanged."""
import json,csv
from pathlib import Path
from urllib.parse import unquote
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE,MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN

ROOT=Path(__file__).resolve().parent
D=json.loads((ROOT/'insights.json').read_text());O=D['overall'];U=O['users'];H=O['watch_hours']
EVENT={e['property']:e for e in D['events']}
WHITE='FFFFFF';NAVY='112D50';ORANGE='F36C2C';INK='173452';MUTED='60748A';LIGHT='F1F5F9';PALE='FFF2E9';LINE='D9E3ED';BLUE='447CB0'
R=Presentation();R.slide_width=Inches(13.333);R.slide_height=Inches(7.5)
R.core_properties.title='Veto Sports | Scale, Momentum & Sponsorship'
R.core_properties.author='Veto Streaming';R.core_properties.subject='Sports portfolio results and sponsorship proposal'
COMMON="Users in this deck means distinct trimmed nonblank cli_ip values on rows with raw_ts_requests > 0. These are client-IP-based reported users, not independently verified people; shared IPs, churn and VPNs may distort identity and geography. Estimated watch hours = sum(raw_ts_requests) × 0.6 / 3,600 = requests / 6,000. The 0.6-second assumption is explicitly requested by the client and differs from a 6-second convention found in an older ETL tool. It is not a validated segment duration or player-measured watch time; retries, errors, delivery duplicates and prefetch cannot be removed using this file. No claims of measured ad impressions, conversions, sponsorship rights or event organisation are made. Source remains unmodified."

def color(s):return RGBColor.from_string(s)
def rect(s,x,y,w,h,c=LIGHT,round=False):
 a=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if round else MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h));a.fill.solid();a.fill.fore_color.rgb=color(c);a.line.fill.background()
 if round:
  try:a.adjustments[0]=.1
  except Exception:pass
 return a
def tx(s,x,y,w,h,t,size=20,c=INK,bold=False,align=None):
 a=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=a.text_frame;tf.word_wrap=True;tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
 for i,line in enumerate(t.split('\n')):
  p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line;p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=color(c);p.space_after=Pt(5)
  if align is not None:p.alignment=align
 return a
def slide(section,title,sub='',note='',proposal=False):
 s=R.slides.add_slide(R.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=color(WHITE)
 rect(s,.55,.4,.09,.24,ORANGE);tx(s,.8,.37,5.9,.28,'VETO  /  SPORTS PARTNERSHIPS',11,NAVY,True);tx(s,10.15,.4,2.45,.25,section.upper(),10,MUTED,True,PP_ALIGN.RIGHT)
 tx(s,.76,1,11.8,1.12,title,32,NAVY,True)
 if sub:tx(s,.8,2.1,11.75,.5,sub,15,MUTED)
 rect(s,.8,7.02,11.75,.012,LINE)
 footer='PROPOSED ACTIVATION / Subject to rights, inventory and measurement agreement' if proposal else 'VETO SPORTS / 18 Sep–14 Nov 2026 / Users are IP-based; watch hours are estimated'
 tx(s,.8,7.13,10.8,.2,footer,9,MUTED);tx(s,11.93,7.1,.6,.25,f'{len(R.slides):02}',11,NAVY,True,PP_ALIGN.RIGHT)
 s.notes_slide.notes_text_frame.text=note+'\n\n'+COMMON
 return s
def metric(s,x,y,w,v,label,detail='',accent=ORANGE,fill=LIGHT):
 rect(s,x,y,w,2.1,fill,True);tx(s,x+.22,y+.18,w-.44,.7,v,40,accent,True);tx(s,x+.22,y+1,w-.44,.48,label,18,NAVY,True)
 if detail:tx(s,x+.22,y+1.59,w-.44,.4,detail,11,MUTED)
def takeaway(s,lead,body,y=6.2):
 rect(s,.8,y,.055,.52,ORANGE);tx(s,1.03,y+.025,2.2,.42,lead.upper(),11,ORANGE,True);tx(s,3.2,y,9.15,.65,body,17,NAVY,True)
def fmt(v):return f'{v/1e6:.2f}M' if v>=1e6 else f'{v/1000:.1f}K' if v>=1000 else f'{v:,.0f}'
def pct(v):return f'{100*v:.1f}%'
def circle(s,x,y,d,c):
 a=s.shapes.add_shape(MSO_SHAPE.OVAL,Inches(x),Inches(y),Inches(d),Inches(d));a.fill.solid();a.fill.fore_color.rgb=color(c);a.line.fill.background();return a
def line(s,x1,y1,x2,y2,c=ORANGE,width=3):
 sh=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2));sh.line.color.rgb=color(c);sh.line.width=Pt(width)

# 01. Bright cover, editorial rather than a data dump.
s=slide('Portfolio review','',note='Opening proposition: a multi-sport streaming portfolio. 3,422,658 users under the stated IP-based reporting definition and 200,815.3191667 estimated hours under the requested 0.6-second formula. The file supports six source property labels over 31 represented dates, not 31 continuous days or a certified tournament schedule. Veto is positioned as a streaming partner; event organisation is not inferred.')
rect(s,8.65,.9,3.9,5.7,NAVY,True);circle(s,11.45,1.05,.55,ORANGE)
tx(s,.8,1.3,7.55,1.9,'Big sports moments.\nA bigger brand opportunity.',37,NAVY,True)
tx(s,.83,3.7,6.8,1.15,'Six properties. Four sports.\nA measurable platform for the next sponsor.',23,INK)
rect(s,.84,5.05,1,.055,ORANGE);tx(s,.84,5.4,6.9,.7,'SPORTS PORTFOLIO & PARTNERSHIP PROPOSAL\n18 September–14 November 2026',12,MUTED,True)
tx(s,9.02,1.7,3.1,.85,'3.42M',49,WHITE,True);tx(s,9.05,2.62,3,.5,'USERS',16,'D4E2EF',True)
rect(s,9.05,3.35,3.05,.015,'47617C');tx(s,9.02,3.85,3.1,.8,'200.8K',40,'FF9B66',True);tx(s,9.05,4.78,3.05,.8,'ESTIMATED\nWATCH HOURS',16,WHITE,True)
tx(s,9.05,5.84,3.0,.35,'0.6 seconds per TS request',10,'D4E2EF')

# 02. Executive story.
s=slide('The opportunity','Scale gets attention.\nThe portfolio gives brands more ways in.','A strong anchor property, a distinct football audience and a valuable returning cohort.',note='Executive overview. Users=3,422,658; hours=200,815.3192; six event labels. The three strategic roles below are recommendations supported by the observed delivery data, not causal findings or proof of commercial outcomes.')
metric(s,.8,2.92,3.76,'3.42M','Users','Deduplicated across the portfolio')
metric(s,4.77,2.92,3.76,'200.8K','Estimated watch hours','Calculated from recorded TS counts',NAVY,PALE)
metric(s,8.74,2.92,3.76,'6','Sports properties','Cricket, football, tennis, weightlifting')
tx(s,.9,5.48,3.55,.5,'CRICKET BUILDS SCALE',16,NAVY,True);tx(s,4.88,5.48,3.55,.5,'FOOTBALL EXTENDS REACH',16,NAVY,True);tx(s,8.85,5.48,3.55,.5,'REPEAT USERS ADD DEPTH',16,NAVY,True)
takeaway(s,'Sponsor opportunity','Build a campaign with an anchor, an extension and a reason to return.')

# 03. Dual scorecard with calibrated bars.
s=slide('Portfolio','Different properties play different roles.','Users show breadth. Estimated watch hours show the distribution of consumption.',note='User bars are scaled to the largest property and are distinct within each property. Per-property users overlap; their sum is not portfolio reach. Estimated hours are additive across properties. Event names follow the file; source match labels are not treated as a verified fixture count.')
ordered=sorted(D['events'],key=lambda e:e['users'],reverse=True)
tx(s,.85,2.78,3.5,.3,'PROPERTY',11,MUTED,True);tx(s,4.35,2.78,4.5,.3,'USERS',11,MUTED,True);tx(s,10.5,2.78,1.9,.3,'EST. HOURS',11,MUTED,True,PP_ALIGN.RIGHT)
for i,e in enumerate(ordered):
 y=3.26+i*.4
 tx(s,.85,y,3.3,.34,e['property'],15,NAVY,True);rect(s,4.4,y+.06,4.6,.12,LIGHT);rect(s,4.4,y+.06,max(.035,4.6*e['users']/ordered[0]['users']),.12,ORANGE if i==0 else BLUE)
 tx(s,9.12,y-.015,1.1,.34,fmt(e['users']),15,NAVY,True,PP_ALIGN.RIGHT);tx(s,10.55,y-.015,1.8,.34,f"{e['watch_hours']:,.0f}",15,NAVY,True,PP_ALIGN.RIGHT)
takeaway(s,'Commercial logic','Use ODI for scale; use the wider portfolio for a more distinctive campaign.')

# 04. Anchor.
odi=EVENT['ODI Tri Series'];cricket=EVENT['ODI Tri Series']['watch_hours']+EVENT['Pak-Sl T20 Series']['watch_hours']
s=slide('The scale anchor','ODI delivered 81.8% of estimated watch hours.','The clearest starting point for a sponsor seeking scale within this portfolio.',note=f"ODI: {odi['users']:,} users; {odi['watch_hours']:,.6f} estimated hours; seven recorded dates. ODI hour share={odi['watch_hours']/H:.8%}. Total cricket hour share={cricket/H:.8%}. No forward audience or sponsorship delivery guarantee implied.")
metric(s,.8,2.95,3.76,'2.63M','ODI users','Across seven recorded dates')
metric(s,4.77,2.95,3.76,'164.2K','Estimated watch hours','ODI Tri Series',NAVY,PALE)
metric(s,8.74,2.95,3.76,'81.8%','Of portfolio hours','A concentrated consumption anchor')
tx(s,.95,5.4,11.35,.55,'ODI + T20 together contributed 91.4% of estimated watch hours.',23,NAVY,True)
takeaway(s,'Sponsor opportunity','Anchor the plan in cricket, then choose where breadth adds value.')

# 05. Peak dates.
top=sorted(D['daily'],key=lambda r:r['watch_hours'],reverse=True)[:3];top2=sum(x['watch_hours'] for x in top[:2])/H
s=slide('High-impact windows','Two dates generated 44.5% of estimated hours.','Timing matters: build the sponsor plan around the strongest observed windows.',note='Top dates by estimated hours: 31 Oct 2026, 52,637.5472; 25 Oct, 36,697.2763; 29 Oct, 20,889.5298. Top two share=44.48606% of portfolio hours. 31 October users=755,965; this is daily distinct users, NOT concurrent users. The data does not establish why these dates peaked. No future schedule is assumed.')
rect(s,.8,2.9,4.1,2.85,NAVY,True);tx(s,1.06,3.15,3.5,.65,'756.0K',39,WHITE,True);tx(s,1.08,3.98,3.5,.5,'USERS ON 31 OCTOBER',15,'D4E2EF',True);tx(s,1.08,4.78,3.45,.85,'52.6K estimated hours\non the same date',18,'FF9B66',True)
for i,x in enumerate(reversed(top)):
 xx=5.45+i*2.3;hh=2.1*x['watch_hours']/top[0]['watch_hours'];rect(s,xx,5.35-hh,1.32,hh,ORANGE if i==2 else BLUE,True);tx(s,xx-.08,5.52,1.55,.35,x['dt'][8:]+' OCT',13,MUTED,True,PP_ALIGN.CENTER);tx(s,xx-.12,5.35-hh-.48,1.65,.38,fmt(x['watch_hours'])+' h',18,NAVY,True,PP_ALIGN.CENTER)
takeaway(s,'Sponsor opportunity','Concentrate key creative around high-impact dates; avoid an even-weight plan.')

# 06. T20 growth.
t20=sorted([x for x in D['matches'] if x['property']=='Pak-Sl T20 Series'],key=lambda x:x['dt']);growth=t20[-1]['users']/t20[0]['users']-1
s=slide('Series momentum','The T20 series finished with 74% more users.','From the first to the third recorded match: a stronger audience by the final window.',note=f"First T20 9 Oct: 87,203 users; second 11 Oct: 96,055; third 13 Oct: 151,425. Growth in match-level distinct users = {growth:.9%}; this does not establish causal growth or retention of the same people. The third match delivered 8,615.427 estimated hours, 44.6502% of T20 hours. All source match labels and dates retained.")
for i,r in enumerate(t20):
 x=.9+i*3.05;yy=4.65-1.7*r['users']/t20[-1]['users'];circle(s,x+1,yy,.18,ORANGE)
 if i<2:
  nxt=4.65-1.7*t20[i+1]['users']/t20[-1]['users'];line(s,x+1.18,yy+.09,x+4.05,nxt+.09,ORANGE,3)
 tx(s,x,yy-.65,2.4,.5,fmt(r['users']),29,NAVY,True,PP_ALIGN.CENTER);tx(s,x,5.1,2.4,.35,['1ST T20','2ND T20','3RD T20'][i],14,MUTED,True,PP_ALIGN.CENTER);tx(s,x,5.5,2.4,.3,['09 OCT','11 OCT','13 OCT'][i],12,MUTED,False,PP_ALIGN.CENTER)
rect(s,10.1,3.1,2.35,2.6,PALE,True);tx(s,10.36,3.48,1.9,.7,'+74%',35,ORANGE,True);tx(s,10.36,4.4,1.82,1.05,'More users\nmatch 3 vs match 1',17,NAVY,True)
takeaway(s,'Sponsor opportunity','A series package can build a narrative toward the later match windows.')

# 07. Non-cricket incrementality.
saff=EVENT['SAFF Championship'];saffonly=next(x['users'] for x in D['exclusive'] if x['property']=='SAFF Championship');noncricket=next(x['users'] for x in D['sports_overlap'] if not x['cricket'])
s=slide('Incremental audience','Football brings a different audience to the plan.','93.2% of SAFF users were observed only in SAFF among these six properties.',note=f"SAFF users={saff['users']:,}; exclusive to SAFF within the observed file={saffonly:,}; exclusivity={saffonly/saff['users']:.8%}. Non-cricket-only users across SAFF, Davis Cup, BJKC and Weightlifting={noncricket:,}; no positive-request observation on either cricket property in this file. This is observed in-file exclusivity, not a lifetime preference, causal acquisition or a promise of incremental ad reach. Properties have different dates; IP churn can inflate apparent differences.")
metric(s,.8,2.95,3.76,'470.2K','SAFF users','Football’s observed footprint')
metric(s,4.77,2.95,3.76,'93.2%','SAFF-only users','Among the six recorded properties',NAVY,PALE)
metric(s,8.74,2.95,3.76,'522.5K','Users outside cricket','Across the non-cricket portfolio')
tx(s,.95,5.4,11.4,.6,'Breadth can add a different audience, rather than simply repeating cricket.',22,NAVY,True)
takeaway(s,'Sponsor opportunity','Pair cricket with football when the brief calls for broader observed reach.')

# 08. Repeat depth.
repeat=next(x for x in D['repeat'] if x['cohort'].startswith('Returning'));single=next(x for x in D['repeat'] if not x['cohort'].startswith('Returning'));intensity=(repeat['watch_hours']/repeat['users'])/(single['watch_hours']/single['users'])
s=slide('Depth','A small returning cohort contributed outsized hours.','201,297 users appeared on more than one recorded date.',note=f"Returning means the same client IP on >1 distinct represented date, not verified people returning. This cohort is {repeat['users']/U:.9%} of users and {repeat['watch_hours']/H:.9%} of estimated hours. Estimated hours per returning identifier / per one-date identifier = {intensity:.9f}. This is a descriptive average across the reporting window, not session length, measured attention or retention causality.")
for i,(name,value) in enumerate([('SHARE OF USERS',repeat['users']/U),('SHARE OF ESTIMATED HOURS',repeat['watch_hours']/H)]):
 y=3.05+i*1.2;tx(s,.85,y,6.7,.35,name,12,MUTED,True);rect(s,.9,y+.52,6.9,.25,LIGHT);rect(s,.9,y+.52,6.9*value,.25,ORANGE);tx(s,8.05,y+.34,1.55,.52,pct(value),28,NAVY,True)
rect(s,10.02,2.98,2.4,2.85,NAVY,True);tx(s,10.3,3.4,1.85,.65,'4.4×',37,WHITE,True);tx(s,10.3,4.3,1.83,1.18,'Estimated hours\nper user vs the\none-date cohort',15,'D4E2EF',True)
takeaway(s,'Sponsor opportunity','Give the campaign recurring creative, not only a single launch message.')

# 09. Regional distinction.
india=next(x for x in D['countries'] if x['category']=='IN');st=D['states']
s=slide('Regional relevance','Uttar Pradesh leads reach.\nJammu & Kashmir leads estimated hours.','A national footprint with different regional strengths to consider.',note='India accounts for 98.8437% of estimated hours (same share as TS counts under a constant conversion). Among source state/UT labels, Uttar Pradesh has the largest distinct positive-request IP count (561,052) and Jammu & Kashmir the largest estimated hours (48,190.8903), 24.2782% of India hours. Country/state derived from source IP location and not independently validated. Values are URL-decoded for display. Users may appear in more than one region. Creative localisation is a proposal; region-targetable inventory is not proved.')
metric(s,.8,2.95,3.65,'561.1K','Uttar Pradesh users','Largest state/UT footprint by users')
metric(s,4.66,2.95,3.65,'48.2K','J&K estimated hours','24.3% of India estimated hours',NAVY,PALE)
metric(s,8.52,2.95,3.98,'98.8%','India share of hours','An India-led delivery footprint')
tx(s,.95,5.4,11.35,.55,'Maharashtra, Delhi, Karnataka and West Bengal add regional breadth.',21,NAVY,True)
takeaway(s,'Sponsor opportunity','Localise the message where useful; confirm targeting availability separately.')

# 10. Device mix.
mix={'Desktop':0,'Mobile + phablet':0,'Smart TV + streaming':0,'Tablet + other':0}
for x in D['devices']:
 k={'desktop':'Desktop','smartphone':'Mobile + phablet','phablet':'Mobile + phablet','smart_tv':'Smart TV + streaming','streaming_device':'Smart TV + streaming'}.get(x['category'],'Tablet + other');mix[k]+=x['watch_hours']
s=slide('Creative planning','Make the brand work across three major screens.','Desktop, mobile and television contributed 98.5% of estimated hours combined.',note='Source-classified device mix uses additive estimated hours, not distinct device-ID counts. Desktop 98,998.629h; mobile+phablet 68,388.2213h; smart TV+streaming 30,494.0212h; other 2,934.4477h. Shares are 49.298%, 34.055%, 15.185% and 1.461%. The raw source has 62.5% blank device_id rows; no cross-device person identity or co-viewing claim is supported. Creative suggestions are proposals, not evidence of inventory.')
for i,(name,hours) in enumerate(list(mix.items())[:3]):
 x=.8+i*3.97;rect(s,x,2.95,3.76,2.73,LIGHT if i!=1 else PALE,True);tx(s,x+.22,3.16,3.3,.55,pct(hours/H),34,ORANGE,True);tx(s,x+.22,3.92,3.3,.55,name,20,NAVY,True);tx(s,x+.22,4.55,3.3,.4,fmt(hours)+' estimated hours',13,MUTED);tx(s,x+.22,5.13,3.3,.35,['Clear, detailed messaging','Concise, legible creative','Big, simple brand assets'][i],13,NAVY,True)
takeaway(s,'Sponsor opportunity','Design a creative system that adapts to the delivery mix.')

# 11. Packages, differentiated.
s=slide('Partnership routes','Choose the role your brand wants to play.','Three proposed routes, built around different sponsor objectives.',note='All partnership routes and placements are proposals. No rate card, existing sponsorship contracts, legal rights, exclusivity, advertising inventory, future event calendar or guaranteed audience were provided. Tennis and weightlifting contexts are proposed thematic associations, not demographic or brand-affinity findings. Agree final commercial scope before sale.',proposal=True)
packs=[('01 / SCALE','Cricket anchor','For a broad visibility brief','ODI-led campaign\nSeries-based creative\nDefined event-window reporting'),('02 / BREADTH','Multi-sport partner','For a broader audience brief','Cricket + football combination\nSelected portfolio extensions\nDeduplicated user reporting'),('03 / CONTEXT','Focused property partner','For a specific brand story','Football, tennis or weightlifting\nA focused creative idea\nA tightly scoped activation')]
for i,(tag,name,goal,body) in enumerate(packs):
 x=.8+i*3.97;rect(s,x,2.95,3.76,3.35,LIGHT if i!=1 else PALE,True);rect(s,x,2.95,3.76,.05,ORANGE);tx(s,x+.22,3.18,3.3,.3,tag,11,ORANGE,True);tx(s,x+.22,3.7,3.3,.8,name,24,NAVY,True);tx(s,x+.22,4.62,3.3,.42,goal,13,MUTED);tx(s,x+.22,5.18,3.3,.95,body,14,NAVY)

# 12. Activation journey.
s=slide('Activation concept','Build anticipation. Own a moment. Extend the story.','An illustrative campaign journey, to shape with the sponsor.',note='These are proposed activities only. Teasers, scorecards, segments, recaps and polls require rights/production approval and technical feasibility. Tracking links or QR codes require instrumentation. The source data does not prove these placements exist or quantify their media value.',proposal=True)
phases=[('BEFORE','Give people a reason to tune in.','Rights-cleared teaser assets\nA consistent brand promise'),('DURING','Make the brand relevant to the moment.','An approved branded segment\nA clear, tracked call to action'),('AFTER','Keep the conversation moving.','Rights-cleared recap creative\nSponsor-owned follow-up')]
for i,(tag,head,body) in enumerate(phases):
 x=.87+i*3.96;circle(s,x,2.95,.5,ORANGE);tx(s,x+.14,3.05,.25,.25,str(i+1),13,WHITE,True)
 if i<2:line(s,x+.65,3.2,x+3.6,3.2,LINE,2)
 tx(s,x,3.8,3.52,.35,tag,12,ORANGE,True);tx(s,x,4.37,3.52,1,head,23,NAVY,True);tx(s,x,5.6,3.52,.95,body,15,MUTED)

# 13. Sponsor accountability.
s=slide('Measurement','A sponsor should get a report, not just a logo.','Agree the success measures before the campaign starts.',note='Available now: IP-defined users, TS-derived estimated hours, and distribution by event/date/device/geography. Not available: impressions, actual ad/player viewing, ad completion, clicks, leads, sales, brand uplift, latency, buffering, concurrent viewers or attribution. New measures must be separately instrumented and agreed. No audience-to-revenue estimate is fabricated.',proposal=True)
rect(s,.8,2.95,5.74,3.24,LIGHT,True);rect(s,6.77,2.95,5.74,3.24,NAVY,True)
tx(s,1.05,3.2,5.2,.38,'PORTFOLIO PERFORMANCE',16,ORANGE,True);tx(s,1.05,3.92,5.15,1.87,'Users and estimated watch hours\nProperty and date performance\nRegional and screen mix\nOne consistent definition of every KPI',19,NAVY)
tx(s,7.02,3.2,5.2,.38,'CAMPAIGN RESULTS TO ADD',16,'FF9B66',True);tx(s,7.02,3.92,5.15,1.87,'Verified placement and ad delivery\nTracked clicks or QR responses\nSponsor-owned lead / sales outcomes\nAn agreed attribution approach',19,WHITE)

# 14. Close.
s=slide('The next partnership','Put your brand into the next sports story.','Start with a focused brief, a rights-cleared scope and a measurable pilot.',note='Recommended next steps. No sponsor names, commercial prices, inventory guarantees or future fixture dates are invented. The historical data supports planning; it does not guarantee campaign outcomes. This deck is a commercial conversation starter and should be paired with a verified rights/inventory sheet before an offer is signed.',proposal=True)
for i,(a,b) in enumerate([('Choose the ambition','Scale, broader reach or a focused sports context.'),('Build the package','Property, dates, creative and approved placements.'),('Agree the proof','Budget, delivery evidence and campaign KPIs.')]):
 y=2.95+i*1.02;tx(s,.85,y,.55,.5,f'{i+1:02}',24,ORANGE,True);tx(s,1.65,y,4.05,.55,a,23,NAVY,True);tx(s,6.1,y+.05,6,.55,b,18,MUTED)
rect(s,.8,6.25,11.7,.47,ORANGE,True);tx(s,1.05,6.33,11.2,.3,'LET’S AGREE A SPONSOR BRIEF AND DESIGN THE PILOT.',17,WHITE,True)

# 15. Exact numbers for review.
s=slide('Appendix','The numbers behind the story.','Exact property totals, calculated with the same user and watch-hour definitions.',note='Event-level users are not additive, because identifiers overlap. Estimated hours reconcile to the overall total. Recorded dates are represented dates, not independently validated live event days. All 8,152,086 source rows were checked and no exact duplicates across the 12 columns were found. Source has zero negative/null raw_ts_requests. Positive request scope is used consistently for user definitions; zero-request-only identifiers excluded.')
cols=[.88,4.42,7.12,10.1];ws=[3.32,2.4,2.7,2.1]
for x,w,t in zip(cols,ws,['PROPERTY','USERS','EST. WATCH HOURS','RECORDED DATES']):tx(s,x,2.84,w,.35,t,11,ORANGE,True)
for i,e in enumerate(ordered):
 y=3.36+i*.4
 if i%2==0:rect(s,.8,y-.04,11.7,.38,LIGHT)
 vals=[e['property'],f"{e['users']:,}",f"{e['watch_hours']:,.1f}",str(e['recorded_dates'])]
 for x,w,t in zip(cols,ws,vals):tx(s,x,y,w,.34,t,14,NAVY,i==0)
rect(s,.8,6.15,11.7,.54,PALE,True);tx(s,1.02,6.24,11.1,.32,'PORTFOLIO: 3,422,658 users  |  200,815.3 estimated watch hours  |  31 recorded dates',17,NAVY,True)

# 16. Definitions, assumption and coverage.
s=slide('Appendix','Clear definitions make the story credible.','What each headline means — and the assumptions behind it.',note=COMMON+'\nSource: Y:\\Veto Logs Backup\\Chinmoy\\sports_all_dates_12_columns.parquet. 8,152,086 rows, 12 columns; source size 165,177,544 bytes. Source interval spans 58 calendar days, but only 31 dates are represented. A coverage audit is not supplied. Device ID is blank on 5,094,230 rows (62.5%); device-level user reach is not used in this deck. Three nonblank device-ID rows have positive requests. No raw IPs or device IDs are included in any presentation or companion output.')
defs=[('Users','Distinct client IPs on positive-TS rows. A reporting proxy, not verified people.'),('Estimated watch hours','TS request count × 0.6 ÷ 3,600. Uses your requested 0.6-second assumption.'),('What hours are not','Player-measured viewing, ad impressions or a guarantee of attention.'),('Comparisons','User groups may overlap; add estimated hours, not property user counts.'),('Coverage','18 Sep–14 Nov 2026, with 31 recorded dates. Completeness is not certified.'),('Commercial scope','Partnerships are proposed; event rights and inventory need separate confirmation.')]
for i,(a,b) in enumerate(defs):
 y=2.9+i*.55;tx(s,.87,y,2.65,.4,a,15,ORANGE,True);tx(s,3.65,y,8.66,.46,b,15,NAVY)
tx(s,.89,6.46,11.3,.3,'Source: sports_all_dates_12_columns.parquet. Original data unchanged. Aggregate audit files included.',11,MUTED)

assert len(R.slides)==16
assert abs(sum(e['watch_hours'] for e in D['events'])-H)<.001
assert abs(sum(mix.values())-H)<.001
assert abs(sum(e['watch_hours'] for e in D['daily'])-H)<.001
assert sum(e['users'] for e in D['sports_overlap'])==U
for s in R.slides:
 for sh in s.shapes:
  assert sh.left>=0 and sh.top>=0 and sh.left+sh.width<=R.slide_width+10000 and sh.top+sh.height<=R.slide_height+10000
target=ROOT/'Veto_Sports_Sponsor_Presentation_v2_Bright.pptx';R.save(target)
for k,v in D.items():
 if isinstance(v,list) and v:
  with (ROOT/(k+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(v[0]));w.writeheader();w.writerows(v)
print(f'Created {len(R.slides)} slides: {target}')
print(f'Users: {U:,} | Estimated hours: {H:,.6f} | All totals reconciled')
