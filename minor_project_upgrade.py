from pathlib import Path
import ast,csv,json,re,zipfile,shutil,hashlib
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle,Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pymupdf
import xml.etree.ElementTree as ET
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import FontProperties

ROOT=Path(r'D:\sam\OTT_Audience_Analytics_Minor_Project')
OUT=ROOT/'History'/'Quality_Upgrade_20261111'
OUT.mkdir(parents=True,exist_ok=True)
TITLE='Role of Audience Analytics in Improving OTT Content Strategy and Viewer Engagement'
library=Path(__file__).with_name('minor_project_build.py')
if not library.exists():library=next(ROOT.glob('History/Previous_material_*/_build/minor_project_build.py'))
code=library.read_text(encoding='utf-8');tree=ast.parse(code)
names={'inline','word_runs','word_paragraph','docx','pdf'}
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in names:
        source=ast.get_source_segment(code,node)
        if node.name=='pdf':
            source=source.replace('Working draft | MBA ITM & Data Science','MBA ITM & Data Science')
            source=source.replace("for k,t in parts:\n", "for k,t in parts:\n        if k=='image':\n            flow.append(RLImage(t,width=446.4,height=201.6));flow.append(Spacer(1,8));continue\n")
        if node.name=='docx':
            source=source.replace("for kind,txt in parts:\n", "for kind,txt in parts:\n        if kind=='image':ps.append(image_xml());continue\n")
        exec(source)

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def image_xml():
    return '''<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" distT="0" distB="0" distL="0" distR="0"><wp:extent cx="5669280" cy="2560320"/><wp:docPr id="1" name="Proposed content decision framework" descr="Validate, compare, explain, decide, evaluate and record; original proposed framework."/><wp:cNvGraphicFramePr/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="0" name="framework.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="figure1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="5669280" cy="2560320"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''

base_csv=next(ROOT.glob('History/Previous_material_*/03_Source_Register.csv'))
with base_csv.open(encoding='utf-8-sig',newline='') as f:
    refs=[r for r in csv.DictReader(f) if r['ID']!='S5']
refs.extend([
 {'ID':'S8','APA-style reference':'Pereira, R., & Tam, C. (2021). Impact of enjoyment on the usage continuance intention of video-on-demand services. Information & Management, 58(7), 103501. doi:10.1016/j.im.2021.103501','URL':'https://research.unl.pt/ws/portalfiles/portal/33026579/Impact_enjoyment_on_usage_intention_video_ondemand.pdf','Material reviewed / evidence level':'Peer-reviewed article; accepted manuscript, methods, structural results and limitations reviewed. Portugal; 205 valid online responses; collection February-June 2018.','Use and limitation':'Cross-sectional perceptions and intention; not observed retention. Enjoyment association with satisfaction and nonsignificant direct continuance relationship. No causal inference or pooled coefficients.','Verified on':'2026-11-11'},
 {'ID':'S9','APA-style reference':'Mondal, D., & Panda, B. K. (2026). Understanding the role of enablers and satisfaction in over-the-top continuance intention among Gen Z in India using an integrated approach. Discover Global Society, 4, Article 26. doi:10.1007/s44282-026-00358-x','URL':'https://link.springer.com/article/10.1007/s44282-026-00358-x','Material reviewed / evidence level':'Peer-reviewed article; methods, results and limitations reviewed. Purposive Indian sample, 203 usable responses; 84% students.','Use and limitation':'Contextual evidence, not representative all-India behavioural retention. Avoid the inconsistent reported mediation percentage and p-values; use unambiguous sample and broad findings.','Verified on':'2026-11-11'}
])
refs=sorted(refs,key=lambda r:r['APA-style reference'])
def reference(r):
    text=r['APA-style reference'];sid=r['ID']
    emph={'S1':'Measuring the business value of recommender systems','S2':'The value of personalized recommendations: Evidence from Netflix','S3':'How Netflix\u2019s recommendations system works','S4':'Artwork personalization at Netflix','S6':'HTTP live streaming','S7':'PLOS One, 21','S8':'Information & Management, 58','S9':'Discover Global Society, 4'}[sid]
    text=text.replace(emph,'<i>'+emph+'</i>')
    if 'doi:' not in text and r['URL'] not in text:text+=' Retrieved from '+r['URL']
    return text

ABSTRACT='''This project examines how audience analytics can support content decisions on over-the-top video platforms. Its business problem is the risk of confusing content demand with promotional exposure, delivery activity or incomplete measurement. A structured narrative review of eight academic, platform and technical sources compares discovery research, independent VOD surveys and streaming definitions. The synthesis distinguishes behavioural activity, perceived satisfaction and continuance intention rather than treating them as interchangeable measures of retention. An Indian study adds local context, while an international comparison identifies limits to generalisation. A worked example converts published model-based recommendation results into transparent indices; a separate hypothetical title calculation demonstrates contribution analysis. Neither is presented as an empirical SmartVOD result. The project proposes a six-stage decision framework: validate, compare, explain, decide, evaluate and record. Recommendations assign owners, investigation triggers and evaluation criteria to promotion, delivery and catalogue decisions. The contribution is a practical connection between data science, information governance and managerial accountability. Reliable content review requires comparable periods, stable asset identity, explicit metric definitions and follow-up evaluation; financial returns and causal improvements are not established by this review.'''

chapters=[
('1. Introduction and business problem','''OTT content teams decide which titles to promote, investigate or retain. Their information may include requests, device identifiers, estimated watch time and category labels. Those measures can move together or disagree. A rise in requests may reflect discovery, repeated polling or a small set of unusually active clients. A category decline may reflect relabelling or an incomplete reporting day. The business problem is therefore how to translate audience evidence into defensible content decisions.

Netflix describes discovery through viewing interactions, title characteristics and contextual ranking. Its artwork account also shows that presentation is part of the discovery process (Chandrashekar, Amat, Basilico, & Jebara, 2017; Netflix, n.d.). These provider accounts motivate examining exposure alongside activity, but do not establish what caused a specific title's performance.

SmartVOD provides the design context for this project. The study does not evaluate its confidential operational dataset. It develops a secondary-research framework relevant to an analyst who must explain content changes to managers. For MBA ITM & Data Science, this combines descriptive and diagnostic analytics with database identity management, data governance and evaluation of business interventions. Its focus is decision quality rather than producing more dashboard indicators.'''),
('2. Objectives, research questions and scope','''Objective 1 is to examine how audience analytics can inform content discovery and promotion. Objective 2 is to evaluate the usefulness and limitations of performance and engagement measures. Objective 3 is to propose a practical framework connecting analytical evidence with accountable action.

The corresponding questions are: How should discovery influence interpretation of title popularity? Which distinctions between activity, satisfaction and returning behaviour matter? How can managers prioritise an action and evaluate its outcome?

The scope covers VOD titles, categories, available audience segments and complete reporting windows. It includes estimated activity and returning identifiers. It excludes a new recommendation model, surveys collected by this project, revenue forecasts and claims of exact playback completion or subscriber churn. These boundaries keep the study feasible and consistent with the required secondary-research approach.'''),
('3. Critical literature review','''A useful distinction is between behavioural evidence and perceived experience. Pereira and Tam (2021) analyse 205 Portuguese survey responses using partial least squares. Satisfaction is associated with continuance intention; enjoyment is associated with satisfaction, while its direct relationship with continuance intention is nonsignificant. You, Song, and Feng (2026) reanalyse 230 archived OTT responses and report different pathways between experience, satisfaction and intention. Both address perceptions rather than observed renewal or playback. Their findings discourage interpreting longer request-derived activity as direct proof of satisfaction.

Mondal and Panda (2026) add Indian context through a purposive Gen Z sample of 203 respondents, 84% of whom are students. Their integrated model includes content availability and personalisation among usage enablers. This adds relevance to content discovery, but the student-heavy sample cannot represent all Indian viewers. Its model and population differ from the Portuguese study; coefficients should not be pooled or ranked as if they measured the same construct. Contemporary publication alone does not resolve sampling limitations.

The survey evidence converges on satisfaction as relevant to intention, but offers no common conversion from satisfaction into delivered minutes. This is an important measurement gap for SmartVOD. Survey instruments can explore experience; server logs can describe operational activity. A business interpretation should triangulate these different forms of evidence rather than substitute one for another.

Jannach and Jugovac (2019) distinguish algorithmic assessment from practical business-value evaluation. That argument challenges a scorecard driven solely by accuracy or volume. Netflix's documentation and artwork discussion provide discovery context, but provider accounts require independent comparison (Chandrashekar et al., 2017; Netflix, n.d.). A platform's description of its own methods is evidence of practice, not universal validation.

Zielnicki et al. (2026) use a structural model with separate validation. Platform ties and model assumptions limit transfer. Together, the reviewed approaches support an original synthesis: interpret a content signal by its definition, exposure and evidence quality before assigning a managerial action.'''),
('4. Research methodology','''The project uses a structured narrative review with purposive selection. Searches and source checks on 11 November 2026 used academic publishers, author repositories and official technical documentation. Inclusion required identifiable authorship, accessible relevant material and a link to discovery, engagement interpretation or metric reliability. Eight sources were retained: independent empirical studies, a research commentary, a working paper, provider documentation and an informational protocol specification.

Selected full-text methods, results and limitations were examined for the empirical studies. A source register records the sections reviewed and evidential limits. Extraction covered setting, sample, method, measured outcome, relevant finding and limitation. Material was coded into discovery, experience, measurement and decision evaluation, then compared thematically. No primary responses or confidential log data were analysed.

The synthesis does not statistically combine path coefficients or effect estimates. Source figures, calculated indices and hypothetical examples are labelled separately. The review is neither exhaustive nor systematic and does not claim meta-analytic certainty. Its analytical output is a proposed framework whose effectiveness remains to be evaluated.'''),
('5. Data analysis and interpretation','''The source measures probability of any play, not watch duration. Table 1 shows model counterfactuals, distinct from its validation experiment. Index = 100 x (1 + reported percentage change / 100). These calculations do not forecast SmartVOD results.'''),
('6. Proposed content-decision framework','''Figure 1 presents the project's original decision loop. Validate checks collection completeness, consistent timezone and stable host-plus-video-key identity. Editorial title changes remain linked to the same asset. Genre, collection and promotional placement are kept distinct so that retagging is not automatically interpreted as a change in audience demand.

Compare uses equal complete periods. Report absolute change alongside percentages; a zero baseline is labelled new activity. Explain examines delivery outcomes, audience concentration and metadata changes before treating a movement as demand. Decide assigns an owner, hypothesis and proposed intervention. Evaluate uses a prespecified comparison or holdout where feasible. Record retains the evidence, decision and result for subsequent review.

Estimated hours should use validated segment-duration information with explicit eligibility and deduplication rules. Retry, range, audio and rendition transfers must not automatically become additional viewing. HLS defines playlist and media-segment structures rather than proof of human attention (Pantos & May, 2017). Known-device averages require the same eligible identifiers in numerator and denominator. Returning-device cohorts need complete follow-up windows; neither measure proves playback completion.

This framework applies descriptive comparison, diagnostic decomposition and cohort reasoning. Technology management contributes lineage, access control and metric ownership. It is an original practical synthesis of the review, rather than a claim to have invented its individual analytical methods.'''),
('7. Results and discussion','''Three findings answer the objectives. For Objective 1, observed popularity depends partly on discovery and exposure, making unqualified winner rankings insufficient. For Objective 2, behavioural engagement, perceived satisfaction, returning identifiers and playback completion are distinct constructs. For Objective 3, a useful decision process needs validation, ownership and evaluation as well as descriptive metrics.

These findings connect the literature with the proposed design without claiming an empirical business improvement. The practical implication is a prioritised investigation list: identify promising discovery opportunities, separate delivery concerns from editorial judgements and test selected actions. A title's apparent weakness should not by itself trigger removal. Costs, rights, availability and strategic audience needs remain relevant management information outside the analysed metrics.

The contribution is strongest as a disciplined interpretation process. It is weaker as an effectiveness claim because no deployment experiment is conducted. Stating that boundary improves the validity of the conclusion rather than diminishing the usefulness of the proposed workflow.'''),
('8. Recommendations and implementation','''Table 2 turns the framework into three owned actions. Triggers are proposed review rules, not statistically validated thresholds. Each organisation should set minimum volumes, comparison periods and tolerances before examining outcomes. Where feasible, an analyst should record the hypothesis and evaluation window in advance to reduce selective reporting.

Start with a governed metric dictionary and identity mapping, then implement title movers and contribution views. Add delivery and concentration checks before automated alerts. Keep inclusive totals available beside any reviewed exclusions. Stakeholder views should use aggregated segments; access to detailed journeys should follow a defined purpose and appropriate controls.

For an intervention, distinguish association from incremental effect. A controlled holdout is preferable when feasible; a before-after comparison alone remains vulnerable to seasonality, release timing and simultaneous campaigns. Report uncertainty and adverse effects alongside a favourable headline. A decision log should include the original signal, owner, action, comparison design and observed outcome, including inconclusive results.'''),
('9. Limitations and conclusion','''The source set is purposive and small. Survey populations and constructs differ, provider accounts may be selective, and model-based estimates depend on assumptions. Publication dates do not indicate when every dataset was collected. The proposed framework has not been empirically tested, and the project makes no claim about improved revenue, subscriber retention or exact playback outcomes.

Audience analytics can support OTT content strategy when its measures answer a defined business question and their limitations remain visible. The review supports combining discovery context, engagement interpretation and reliable operational evidence. Stable identities and complete windows enable comparison; contribution analysis helps explain movements; owned actions and evaluation close the management loop. This approach links MBA ITM governance with data-science reasoning while preserving the distinction between a useful proposal and a demonstrated commercial result.'''),
]

# Add practical depth through original reasoning rather than repeating source summaries.
chapters[2]=(chapters[2][0],chapters[2][1]+'''\n\nThe managerial gap is not simply an absence of data. It is an absence of a consistent bridge between an observed signal and a justified decision. An analyst needs to state whether the immediate question concerns discovery, experience, delivery or continued activity. Evidence appropriate for one question may be insufficient for another. A regional difference, for example, can motivate a targeted review without proving a stable regional preference. This framing turns uncertainty into a specific follow-up question.''')
chapters[5]=(chapters[5][0],chapters[5][1]+'''\n\nA minimal operational scorecard should show estimated hours, known-identifier reach, estimated minutes per known identifier, return activity, catalogue coverage and delivery failure rate. For minutes per device, divide eligible estimated minutes belonging to known Device IDs by distinct eligible known Device IDs. Missing identifiers remain a separate coverage measure; assigning their activity to the numerator alone inflates the average. An IP-based view should remain separately labelled because shared addresses can combine users.\n\nFor returning activity, define the original cohort, title identity and follow-up window before calculation. Include baseline identifiers only where the dataset covers the full follow-up window; identifiers not observed again remain in the denominator as nonreturners. New identifiers entering later must not inflate that baseline. Display the cohort size and uncertainty alongside the rate. These rules translate cohort analysis and data-management knowledge into a reproducible procedure, without claiming that device return equals subscription renewal.''')
chapters[7]=(chapters[7][0],chapters[7][1]+'''\n\nA workable review starts with a short weekly shortlist rather than automatic action on every alert. The analyst documents the largest absolute movements and flags small baselines. The content owner checks release timing and availability; operations checks collection and failures. The team then chooses a limited intervention, keeps an unchanged comparison where feasible and records whether the outcome supports the initial hypothesis. An inconclusive result should lead to refinement or further observation, not a retrospective change to the success criterion. This process makes analytical work accountable while preserving managerial judgement.''')

example_rows=[['Policy','Reported change','Calculated index'],['Current system','Baseline','100'],['Matrix factorisation','-4%','96'],['Popularity-based','-12%','88'],['Random','-16%','84']]
example_note='''Note. Calculated from Zielnicki et al. (2026), section 5.1.1, Table 1; baseline = 100.'''
example_analysis='''This comparison motivates testing discovery policy. Title-level acquisition values are not disclosed, so it cannot determine a content budget.

Illustrative title calculation, not research findings: suppose a title falls from 200 to 150 estimated hours while its category falls by 80 hours. The title change is -50 hours, or -25%, contributing 62.5% of the category's net decline. Other titles must sum to -30 hours for reconciliation. Investigate collection, placement and audience concentration before an editorial response. Where opposing changes nearly cancel, show contributions separately instead of unstable percentages of a near-zero net change.'''

action_rows=[['Owner and review trigger','Action and evaluation'],['Content manager: limited reach with stronger eligible engagement','Run a bounded discovery test. Compare incremental eligible reach/activity with a holdout where feasible; guard against errors and concentrated traffic.'],['Data/operations lead: decline alongside missing data or failures','Reconcile collection, mapping and delivery first. Evaluate restored completeness and delivery quality; do not assume restored demand.'],['Catalogue manager: persistent weak coverage after validation','Review genre separately from placement, alongside rights and cost. Record the decision and follow-up; avoid automatic removal based on hours alone.']]

# Original diagram, drawn at its intended physical size with Times New Roman labels.
font=FontProperties(fname='C:/Windows/Fonts/times.ttf',size=12)
bold=FontProperties(fname='C:/Windows/Fonts/timesbd.ttf',size=12)
fig,ax=plt.subplots(figsize=(6.2,2.8));ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
positions=[(.17,.75),(.5,.75),(.83,.75),(.83,.25),(.5,.25),(.17,.25)]
labels=[('1. Validate','Data coverage'),('2. Compare','Equal windows'),('3. Explain','Signals and risks'),('4. Decide','Owner and action'),('5. Evaluate','Prespecified test'),('6. Record','Evidence and result')]
for (x,y),(a,b) in zip(positions,labels):
    ax.add_patch(FancyBboxPatch((x-.145,y-.17),.29,.34,boxstyle='round,pad=0.007',facecolor='#f3f4f5',edgecolor='#333333',linewidth=.8))
    ax.text(x,y+.045,a,ha='center',va='center',fontproperties=bold)
    ax.text(x,y-.065,b,ha='center',va='center',fontproperties=font)
for i in range(5):
    x1,y1=positions[i];x2,y2=positions[i+1]
    if y1==y2:
        sign=1 if x2>x1 else -1;start=(x1+sign*.15,y1);end=(x2-sign*.15,y2)
    else:start=(x1,y1-.18);end=(x2,y2+.18)
    ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'->','color':'#333333','lw':1})
ax.annotate('',xy=(.17,.57),xytext=(.17,.43),arrowprops={'arrowstyle':'->','color':'#555555','lw':.8,'linestyle':'--'})
fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.98)
diagram=OUT/'Proposed_Framework.png';fig.savefig(diagram,dpi=200);fig.savefig(OUT/'Proposed_Framework.svg');plt.close(fig)

report=[('title',TITLE),('body','Minor Project Report\nMBA ITM & Data Science\n11 November 2026'),('break',''),('heading','Abstract'),('body',ABSTRACT)]
for i,(h,t) in enumerate(chapters):
    report.extend([('heading',h),('body',t)])
    if i==4:report.extend([('caption','Table 1\n<i>Worked comparison of published recommendation estimates</i>'),('table',example_rows),('body',example_note),('body',example_analysis)])
    if i==5:report.extend([('image',str(diagram)),('body','<i>Figure 1.</i> Proposed framework developed from the review.'),('body','Note. Original conceptual framework; not an empirically evaluated process.')])
    if i==7:report.extend([('caption','Table 2\n<i>Proposed action ownership and evaluation</i>'),('table',action_rows),('body','Note. Original recommendations informed by the review; triggers require local definition and evaluation.')])
report.extend([('break',''),('heading','References')]);report.extend(('ref',reference(r)) for r in refs)

# Adapt the audited synopsis to the deeper eight-source review, retaining all nine requested fields.
source_syn=ROOT/'Project_Synopsis.docx'
if not source_syn.exists():source_syn=next(ROOT.glob('History/Before_quality_upgrade_*/Project_Synopsis.docx'))
with zipfile.ZipFile(source_syn) as z:x=ET.fromstring(z.read('word/document.xml'))
syn_sections=[];current=None
for p in x.findall('.//w:p',NS):
    text=''.join(p.itertext())
    if p.find('w:pPr/w:keepNext',NS) is not None:
        if text=='References':break
        syn_sections.append([text,[]]);current=syn_sections[-1]
    elif current:current[1].append(text)
synopsis=[]
for h,paras in syn_sections:
    text='\n\n'.join(paras)
    if h=='Abstract':text=ABSTRACT
    elif h=='Project Area (Specialization/Stream)':text='MBA ITM & Data Science\nBusiness Intelligence, Audience Analytics and OTT Content Strategy.'
    elif h=='Why this topic has been chosen':text=text.replace('Research also supports considering catalogue diversity and coverage alongside popularity or predictive accuracy (Han & Yamana, 2017).','Independent research connects perceived enjoyment with satisfaction while distinguishing satisfaction from continuance intention (Pereira & Tam, 2021).')
    elif h=='Scope of the Project':text=text.replace('(Netflix, n.d.; Chandrashekar, Amat, Basilico, & Jebara, 2017)','(Chandrashekar, Amat, Basilico, & Jebara, 2017; Netflix, n.d.)')
    elif h=='Methodology':text='''The project uses a structured narrative review of eight purposively selected academic, platform and technical sources. Selected full-text methods, results and limitations are compared through themes of discovery, experience,measurement and decision evaluation. Independent evidence includes Indian Gen Z and Portuguese VOD studies (Mondal & Panda, 2026; Pereira & Tam, 2021). Playlist and media distinctions follow Pantos and May (2017). A source register records evidence depth and limitations.\n\nA worked example transparently converts published model-counterfactual percentage changes into indices (Zielnicki et al., 2026). A separate hypothetical title calculation demonstrates contribution analysis without presenting invented figures as findings. The synthesis develops a six-stage decision framework and recommendations with owners, triggers and evaluation criteria. No primary surveys, confidential-log empirical analysis, trained prediction model or measured commercial uplift is claimed. The narrative review is not exhaustive or systematic.'''
    else:text=text.replace('seven academic','eight academic').replace('Seven sources','Eight sources')
    text=text.replace('experience,measurement','experience, measurement')
    synopsis.extend([('heading',h),('body',text)])
synopsis.append(('heading','References'));synopsis.extend(('ref',reference(r)) for r in refs)

def finish_word(path,parts):
    docx(path,parts)
    with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
    files['word/footer1.xml']=files['word/footer1.xml'].replace(b'Working draft | ',b'MBA ITM &amp; Data Science | ')
    # Ensure the physical Word grid matches each table's actual column count.
    document_xml=ET.fromstring(files['word/document.xml'])
    for tbl in document_xml.findall('.//w:tbl',NS):
        cells=tbl.find('w:tr',NS).findall('w:tc',NS)
        widths=(3600,2700,2726) if len(cells)==3 else (3000,6026)
        grid=tbl.find('w:tblGrid',NS)
        for element in list(grid):grid.remove(element)
        for width in widths:ET.SubElement(grid,'{'+NS['w']+'}gridCol',{'{'+NS['w']+'}w':str(width)})
    for prefix,uri in [('w',NS['w']),('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships'),('wp','http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'),('a','http://schemas.openxmlformats.org/drawingml/2006/main'),('pic','http://schemas.openxmlformats.org/drawingml/2006/picture')]:ET.register_namespace(prefix,uri)
    files['word/document.xml']=ET.tostring(document_xml,encoding='utf-8',xml_declaration=True)
    if any(k=='image' for k,_ in parts):
        rel=files['word/_rels/document.xml.rels'].decode().replace('</Relationships>','<Relationship Id="figure1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/framework.png"/></Relationships>')
        files['word/_rels/document.xml.rels']=rel.encode()
        types=files['[Content_Types].xml'].decode().replace('</Types>','<Default Extension="png" ContentType="image/png"/></Types>')
        files['[Content_Types].xml']=types.encode();files['word/media/framework.png']=diagram.read_bytes()
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,data in files.items():z.writestr(n,data)

def flatten(parts):
    out=[]
    for k,t in parts:
        if k=='break':continue
        if k=='image':
            out.append('\n'.join(a+'\n'+b for a,b in labels));continue
        if k=='table':out.append('\n'.join(' | '.join(row) for row in t))
        else:out.append(re.sub('</?i>','',t))
    return '\n\n'.join(out)

# The previous renderer handled only two-column tables: retain its style and generalise widths.
pdf_function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='pdf')
pdf_source=ast.get_source_segment(code,pdf_function)
pdf_source=pdf_source.replace('Working draft | MBA ITM & Data Science','MBA ITM & Data Science')
pdf_source=pdf_source.replace("for k,t in parts:\n", "for k,t in parts:\n        if k=='image':\n            flow.append(RLImage(t,width=446.4,height=201.6));flow.append(Spacer(1,8));continue\n")
pdf_source=pdf_source.replace('colWidths=[135,316.276]','colWidths=([180,135,136.276] if len(t[0])==3 else [150,301.276])')
exec(pdf_source)
# Likewise generalise Word column grids before generating its publication-quality tables.
docx_function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='docx')
docx_source=ast.get_source_segment(code,docx_function)
docx_source=docx_source.replace("for kind,txt in parts:\n", "for kind,txt in parts:\n        if kind=='image':ps.append(image_xml());continue\n")
docx_source=docx_source.replace('2700 if j==0 else 6326','(3600,2700,2726)[j] if len(row)==3 else (3000 if j==0 else 6026)')
docx_source=docx_source.replace("'<w:tblGrid><w:gridCol w:w=\"2700\"/><w:gridCol w:w=\"6326\"/></w:tblGrid>'", "('<w:tblGrid><w:gridCol w:w=\"3600\"/><w:gridCol w:w=\"2700\"/><w:gridCol w:w=\"2726\"/></w:tblGrid>' if len(txt[0])==3 else '<w:tblGrid><w:gridCol w:w=\"3000\"/><w:gridCol w:w=\"6026\"/></w:tblGrid>')")
# String literal is embedded in a larger concatenation; fix the grid independently in final XML below.
exec(docx_source)

for name,parts in [('Project_Synopsis',synopsis),('Project_Report',report)]:
    finish_word(OUT/(name+'.docx'),parts);pdf(OUT/(name+'.pdf'),parts)
    (OUT/(name+'.txt')).write_text(flatten(parts),encoding='utf-8')

report_text=flatten(report)
count=lambda t:len(re.findall(r"\b[\w'-]+\b",t))
all_words=count(report_text)
assert 2000<=all_words<=3500,('Complete report word count',all_words)
assert len(refs)==8 and len(TITLE.split())==12
source_header=['ID','APA-style reference','URL','Material reviewed / evidence level','Use and limitation','Verified on']
with (OUT/'Source_Register.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=source_header);writer.writeheader();writer.writerows(refs)

# These are preparation questions, never substituted for actual portal viva questions.
viva='''VIVA PREPARATION - PRACTICE ONLY
1. What business problem does the project address?
It addresses the risk of confusing operational activity and discovery exposure with genuine
content preference. The proposed framework links a validated signal with an owned action.

2. Why use secondary research, and what did you actually analyse?
The supplied guidelines require secondary research. Eight selected sources were compared
thematically; no new survey or confidential viewer dataset was analysed.

3. How do retention, satisfaction and returning devices differ?
Playback retention needs position/progression data; satisfaction is a measured perception;
returning devices indicate repeated activity by known identifiers. They are not interchangeable.

4. What do the 100, 96, 88 and 84 indices show?
They normalise published model-counterfactual changes, not raw watch hours or SmartVOD
uplift. 100 x (1 + change/100) converts -4% to 96, for example.

5. What is the contribution and its principal limitation?
The contribution is an original practical synthesis with validation, ownership and evaluation.
It is not an empirically validated intervention or an invention of the underlying methods.

Be ready to explain source selection, the Indian sample limitation, the hypothetical title
example and why a before-after comparison alone does not establish causal improvement.
The institution's five actual viva questions must be answered separately when released.
'''
(OUT/'Viva_Practice.txt').write_text(viva,encoding='utf-8')
print(json.dumps({'complete_report_words_including_tables_captions_references':all_words,'sources':len(refs),'output':str(OUT)},indent=2))
