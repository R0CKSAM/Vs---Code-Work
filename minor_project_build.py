from pathlib import Path
import re, csv, json, zipfile, shutil
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT=Path(r'D:\sam\OTT_Audience_Analytics_Minor_Project')
OUT.mkdir(exist_ok=True)
backup=OUT/'_history'/'before_audit_20261111'
if not backup.exists():
    backup.mkdir(parents=True)
    for previous in OUT.iterdir():
        if previous.is_file(): shutil.copy2(previous,backup/previous.name)
TITLE='Role of Audience Analytics in Improving OTT Content Strategy and Viewer Engagement'
refs=[
('S1','Jannach, D., & Jugovac, M. (2019). Measuring the business value of recommender systems. arXiv preprint arXiv:1908.08328.','https://arxiv.org/abs/1908.08328v3','Research commentary; full-text introduction and sections 3.4 and 4 reviewed','Business value measurement; offline performance does not establish business impact. Cites 2019 arXiv version, not the 2020 journal version.'),
('S2','Zielnicki, K., Aridor, G., Bibaut, A., Tran, A., Chou, W., & Kallus, N. (2026). The value of personalized recommendations: Evidence from Netflix (Version 5). arXiv preprint arXiv:2511.07280.','https://arxiv.org/abs/2511.07280v5','Working paper; full-text introduction, sections 5.1 and 5.2 reviewed; arXiv v5 posted June 8, 2026; HTML manuscript internally dated August 24, 2026','Model-based context-specific estimates, not a transferable forecast. Authors disclose Netflix employment, financial interests or prior contracting.'),
('S3','Netflix. (n.d.). How Netflix\u2019s recommendations system works. Retrieved November 11, 2026, from https://help.netflix.com/en/node/100639/','https://help.netflix.com/en/node/100639/','Platform-authored documentation reviewed','Signals and ranking used in content discovery; provider perspective.'),
('S4','Chandrashekar, A., Amat, F., Basilico, J., & Jebara, T. (2017, December 7). Artwork personalization at Netflix. Netflix Technology Blog.','https://netflixtechblog.com/artwork-personalization-c589f074ad76','Platform technical article; introduction reviewed','Artwork and discovery; placement and representation can affect observed activity.'),
('S5','Han, J., & Yamana, H. (2017). A survey on recommendation methods beyond accuracy. IEICE Transactions on Information and Systems, E100.D(12), 2931\u20132944. doi:10.1587/transinf.2017EDR0003','https://www.jstage.jst.go.jp/article/transinf/E100.D/12/E100.D_2017EDR0003/_article','Peer-reviewed survey; abstract and bibliographic record reviewed','Diversity, novelty and coverage; definitions and trade-offs.'),
('S6','Pantos, R., & May, W. (2017). HTTP live streaming (RFC 8216). RFC Editor. doi:10.17487/RFC8216','https://datatracker.ietf.org/doc/html/rfc8216','Informational protocol specification; playlist and media-segment sections reviewed','Playlist/media distinction and segment durations; not a human-viewing measurement specification.'),
('S7','You, Y.-Q., Song, H.-H., & Feng, Y.-L. (2026). Examining the influence of user experience on functional value, satisfaction, and usage intention in OTT video platforms. PLOS One, 21(5), e0350557. doi:10.1371/journal.pone.0350557','https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0350557','Peer-reviewed article; abstract, archived-data methods, sample description and measurement limitations reviewed','Independent OTT perspective; archived responses from 230 users, skewed toward younger and educated respondents; associations do not establish causal effects or validate server-log satisfaction proxies.'),
]

abstract='''This study examines how audience analytics can support content strategy and viewer engagement on over-the-top video platforms. It addresses a managerial problem: content teams must decide which titles to promote, investigate or retain while working with measures that may describe requests, devices or estimated viewing rather than individual people. The study uses a structured narrative review of seven selected academic, platform and technical sources. It does not collect survey responses, conduct interviews or analyse confidential viewer logs as research evidence. The review considers content discovery, recommendation evaluation, catalogue diversity and the interpretation of delivery data. Its synthesis distinguishes business outcomes from activity measures and perceived satisfaction from observed requests. It proposes a content-centred decision framework linking stable asset identity, comparable reporting periods, audience measures, estimated engagement and delivery quality. SmartVOD provides the design context for the proposed framework, rather than an independently evaluated case study. Recommended outputs include title and category movers, contribution-to-change analysis, returning-identifier cohorts and alerts requiring analyst review. The study distinguishes observed association from causal impact and separates repeat activity from exact playback retention. For MBA ITM and Data Science practice, its contribution is a practical method for connecting data governance and analytical methods with content decisions. Implementation effectiveness and financial returns remain questions for subsequent evaluation.'''

sections=[
('1. Introduction and business context','''OTT content decisions involve competing priorities: attracting an audience, helping viewers discover relevant titles and using limited promotional space responsibly. A platform may contain popular releases, specialist programmes and older catalogue material. A simple list of the most requested videos cannot explain whether a title is emerging, declining, reaching a new segment or receiving repeated automated checks. Managers therefore need interpretable evidence linked to specific decisions.

Netflix describes discovery as using viewing interactions, title information and contextual signals to rank content. Its documentation demonstrates that discovery is more than a static popularity list (Netflix, n.d.). For this project, that observation motivates a distinction between measuring content activity and recommending a managerial action. The proposed analysis must preserve that distinction when explaining results to nontechnical stakeholders.

This topic connects information technology management with data science. Technology management concerns the reliability, ownership and use of information systems. Data science contributes comparable measures, segmentation, anomaly review and explicit uncertainty. The business purpose is to improve the quality of content decisions, rather than increase the number of dashboard charts. SmartVOD is used as the practical design context for that purpose; no internal numerical results are claimed in this report.'''),
('2. Problem statement, objectives and scope','''The central problem is that an apparent content-performance change can have several explanations. Demand may have changed, a title may have moved between categories, promotional exposure may have changed, or collection may be incomplete. Without consistent definitions, a manager could promote weak content, overlook a promising title or interpret a delivery problem as declining audience interest.

The first objective is to examine how audience analytics can support OTT content selection and promotion. The second is to evaluate the usefulness and limitations of content-performance and engagement measures. The third is to recommend a practical framework that connects analytical evidence with content decisions.

The research questions are: Which measures are useful for comparing titles and categories? What prevents request-derived measures from being interpreted as exact audience retention? How should a dashboard present changes so that a manager can decide what to investigate or test? The scope covers VOD content strategy. It excludes a financial valuation of a specific catalogue, the construction of a recommendation algorithm and claims about subscriber churn without account-level evidence.'''),
('3. Literature review and background','''Jannach and Jugovac (2019) review the measurement of business value in recommender systems. They distinguish algorithm evaluation from evidence about practical business outcomes. This supports a cautious interpretation of a dashboard: improved ranking accuracy or a larger watch-time total does not itself establish a profitable business intervention. Their review is used here for its measurement argument, rather than as a source of expected returns for SmartVOD.

Zielnicki et al. (2026) examine personalized recommendations using Netflix viewership data and a structural model. Their abstract reports that replacing the existing recommender with alternative approaches would reduce engagement in their analysed setting, and identifies effective targeting as an important mechanism. These findings support investigating discovery and audience matching. They do not establish that an equivalent uplift would occur on another platform, or that an observational dashboard can reproduce their causal analysis.

Netflix's own documentation describes the use of viewing history, ratings, title attributes and context in recommendation ranking (Netflix, n.d.). Chandrashekar, Amat, Basilico, and Jebara (2017) discuss personalized artwork as part of discovery. Together, these provider accounts suggest that observed title activity should be interpreted alongside how content is presented. They also have a limitation: they describe one provider's practices and should not be treated as independent proof that every platform follows the same design.

Han and Yamana (2017) review recommendation approaches that consider diversity, novelty and catalogue coverage alongside accuracy. Their discussion makes a popular-title-only scorecard inadequate for this project's proposed business framework. A platform may wish to expose relevant catalogue breadth as well as reinforce current leaders. The trade-off should be made explicit instead of hidden within a single performance score.

Pantos and May (2017) describe HLS playlists and media segments, including segment-duration information. This technical distinction matters because a playlist request and a media request represent different delivery actions. The specification does not define proof of human attention. The present report therefore treats server-side evidence as a source of operational estimates and avoids equating each request with a view.'''),
('4. Research methodology','''The study follows a structured narrative review based entirely on secondary sources. Seven sources were selected purposively for relevance to recommendation value, content discovery, catalogue evaluation, perceived engagement or the interpretation of streaming delivery data. Search and verification were conducted on 11 November 2026 using author repositories, academic publishers, official platform documentation and the RFC publication record. Foundational sources were retained where they explained an enduring measurement issue; two 2026 papers provided contemporary perspectives.

The review examined abstracts and bibliographic records, selected full-text sections of Jannach and Jugovac, Zielnicki et al. and You et al., and relevant platform and protocol sections. Han and Yamana were reviewed through the publisher abstract. Search concepts included OTT audience engagement, recommendation business value, discovery and streaming measurement. Sources needed identifiable authorship and accessible evidence relevant to the questions; news summaries and unsupported uplift claims were excluded. This purposive review is not exhaustive or systematic. The companion register records what was actually reviewed.

Analysis grouped the material into four themes: business-value measurement, content discovery, catalogue breadth and metric reliability. These themes informed an original proposed decision framework. No survey, interview, experiment or confidential operational dataset was used as empirical research evidence. Consequently, the results below are a conceptual synthesis and design recommendations. They are not measured findings from a SmartVOD deployment. This boundary keeps the method consistent with the supplied minor-project requirement for secondary research.'''),
('5. Proposed analytical framework','''The proposed framework begins with a stable content identity. A video key combined with its host can distinguish assets while retaining a history of title labels. An editorial or SEO title change should not create artificial growth by splitting one asset into two records. Conversely, identical title text should not automatically merge different assets. A manager should be able to inspect the identity rule behind any comparison.

Second, maintain separate fields for catalogue genre, collection membership and promotional placement. A sports title can legitimately appear in a banner and a themed collection. Those tags describe different business dimensions. When a record has a logged category, its estimated hours can be assigned to that category for reconciliation. Counts of distinct assets across overlapping memberships must be labelled nonadditive. A change caused by retagging should be identified before interpreting category demand.

Third, define a concise scorecard. Reach uses distinct known identifiers, reported separately for Device ID and client IP. Activity uses estimated segment-derived hours with the method displayed. Engagement uses estimated minutes per known identifier and a distribution, rather than only an average. Repeat interest uses a defined returning-identifier cohort. Delivery quality uses request outcomes and error rates. These are proposed operational measures; none is automatically equivalent to people, satisfaction or subscriber retention.

Fourth, compare complete and equivalent periods. A seven-day window should normally be compared with the previous seven days using the same timezone and filtering rules. The dashboard should identify incomplete days, missing partitions and changed definitions before displaying growth. A large percentage change from a tiny baseline should appear as an emerging signal requiring review, rather than a decisive performance winner.'''),
('6. Analysis and interpretation: proposed insight outputs','''The first output is a title-movers table. Each row should show current and previous estimated hours, absolute change, percentage change, known audience counts and delivery quality. Where the previous value is zero, display a new-activity label instead of an infinite percentage. Minimum-volume rules should be configurable and described as analyst choices, not statistically validated thresholds.

The second output is contribution-to-change analysis. For each category, calculate every title's current value minus its previous value and reconcile the sum with the category difference. Show the largest positive and negative contributions separately because opposing movements can cancel. If the category net change is close to zero, avoid dividing each contribution by that net total: it creates unstable percentages. This makes the business explanation both clearer and auditable.

The third output is a reach-and-engagement matrix. Broad reach with limited estimated minutes suggests a title worth investigating for audience fit or delivery issues. Narrow reach with stronger sustained activity suggests a possible discovery opportunity. Broad reach and strong engagement indicate an established performer. These positions generate questions for a content team; they do not prove that a programme should be purchased or removed.

The fourth output concerns repeat interest. Define a cohort of known devices active on a title in an initial window, then measure the proportion observed again on that title in a stated later window. Require complete follow-up coverage and disclose identifier gaps. This is returning-device activity, not an account-retention measure. A separate playback-position event stream would be needed to establish minute-level audience retention and completion reliably.

The fifth output compares title performance across region and device segments. Show each segment's volume and share, as well as its movement over time. A title can gain share while losing hours if the overall platform declines faster. Both measures are therefore necessary. Avoid interpreting a regional association as an inherent preference without checking catalogue availability, promotion and collection quality.

The sixth output is a trust panel attached to every insight. It should show data freshness, identifier coverage, unknown metadata, delivery errors and audience concentration. Continuous simultaneous fetching or unusually concentrated activity should prompt review. Such patterns are indicators, not proof of a bot or a particular organisation. Keep inclusive totals available beside any reviewed analytical exclusion so that stakeholders can understand its effect.'''),
('7. Results and discussion','''The secondary-research synthesis yields three findings aligned with the objectives. First, audience evidence can inform discovery decisions, but activity totals alone do not isolate a title's intrinsic appeal from its exposure or targeting (Netflix, n.d.; Zielnicki et al., 2026). Second, metric choice changes interpretation: recommendation accuracy, catalogue coverage, perceived satisfaction and returning identifiers describe different outcomes (Han & Yamana, 2017; You et al., 2026). Third, evidence about business value requires more than a favourable dashboard trend (Jannach & Jugovac, 2019). These findings motivate the proposed framework; they do not validate its effectiveness.

The synthesis suggests that content analytics should be organised around decisions and evidence quality. A trend should be followed by a question, an owner and a testable action. A dashboard alone should not be credited with improving engagement before that improvement has been evaluated.

For example, a manager could shortlist an underexposed title for a controlled promotional test. The proposed dashboard would document the initial evidence, while a later evaluation would assess the intervention. This recommendation is an original application of the reviewed themes. It is not a claim that the reviewed sources tested this precise workflow or that SmartVOD has already produced an uplift.

Resource allocation should also acknowledge uncertainty. A high-volume decline deserves urgent investigation when delivery errors rise at the same time, but that coincidence is not causal proof. A category's growth may reflect a temporary event or a changed placement. The useful managerial output is therefore a prioritized investigation list with traceable evidence, rather than an automatic instruction to acquire, remove or promote content.'''),
('8. Recommendations and implementation roadmap','''Begin with a governed metric dictionary and an approved content-identity table. Assign owners for source completeness, catalogue metadata and business interpretation. Publish the distinction between requests, estimated viewing, identifiers and accounts. Record changes to definitions so that a reporting update is not mistaken for an audience change.

Next, implement the title-movers and contribution views before adding complex prediction. Require every insight to display comparison windows, actual values, data coverage and a drill-through explanation. Offer plain-language summaries such as a decline concentrated in three titles, supported by the underlying records. Do not generate unsupported explanations for why viewers behaved a certain way.

Then establish a weekly content-review process. Content managers review the strongest signals, select a small number of actions and record the hypothesis, decision owner and evaluation window. Technology staff investigate delivery or collection issues separately where appropriate. This gives the analytical system an operational purpose without confusing its measurements with editorial judgement.

Finally, add player events for playback position, duration, pause, completion, startup and buffering if those decisions require them. Join only the identifiers needed for the stated purpose, limit access to detailed journeys and use aggregated stakeholder reports. Evaluate future models with holdout periods and clear success criteria. Any commercial benefit should be measured through a suitable experiment or justified evaluation design, rather than assumed from correlation.'''),
('9. Limitations and conclusion','''This project uses a small purposively selected source set, including an abstract-only survey review and provider-authored material. It is a narrative review, not an exhaustive survey or meta-analysis. Recommendation research from a large subscription platform may not transfer directly to a smaller advertising-supported service. Netflix-linked authorship and financial interests in the working paper require attention when assessing independence. The separate survey-based study concerns perceptions and intention rather than actual continued viewing. The proposed framework has not been empirically evaluated here, and no forecast of revenue, churn or engagement uplift is made.

The main conclusion is that useful OTT content analytics requires trustworthy comparisons and a clear connection between evidence and action. Stable content identities, distinct category meanings, transparent estimates and complete reporting windows provide the foundation. Title movers, contribution analysis and returning-identifier cohorts can then support a disciplined content-review process. For MBA ITM and Data Science, the practical contribution is a framework that combines information governance, analytical interpretation and managerial accountability while preserving the limits of the available evidence.'''),
]

# Keep reviewed evidence distinct from the original proposed framework.
sections[2]=(sections[2][0], sections[2][1]+'''\n\nYou, Song, and Feng (2026) reanalyse archived survey responses from 230 OTT users using partial least squares structural equation modelling. They report associations between perceived experience, satisfaction and usage intention. The sample is concentrated among younger, educated respondents. This independent perspective complements platform-authored evidence, but self-reported cross-sectional relationships neither establish causality nor validate watch time as a measure of satisfaction.''')
sections[4]=(sections[4][0], sections[4][1]+'''\n\nThe design applies descriptive analytics through period comparisons, diagnostic analytics through contribution decomposition, and cohort analysis through returning identifiers. Database management contributes stable keys and auditable lineage. IT governance contributes access controls, metric ownership and change records. These links demonstrate the application of MBA ITM and Data Science knowledge; predictive accuracy or a trained model is not claimed.''')
metric_rows=[
['Measure / analytical method','Proposed definition and interpretation'],
['Period movement','Change = current hours minus previous hours; change % = 100 x change / previous hours when the baseline is positive. Compare complete equal windows.'],
['Contribution decomposition','Sum title-level changes within a category and reconcile with its net change. Report opposing contributions separately.'],
['Estimated viewing','Sum validated per-segment durations / 3,600 after documented deduplication and request eligibility checks. A fixed duration is only an explicitly labelled proxy.'],
['Minutes per known device','60 x estimated hours for known Device IDs / distinct known Device IDs, using the same scope in numerator and denominator. Not average session duration.'],
['Returning-device cohort','100 x baseline devices observed on the same title in a complete follow-up window / eligible baseline devices. Not playback completion or subscriber retention.'],
['Delivery failure rate','100 x failed eligible media requests / all eligible media requests. Report status and abort detail; successful delivery alone does not prove playback.'],
]
sections[5]=(sections[5][0],sections[5][1]+'''\n\nTable 1 specifies the proposed calculations. Playlist polls, repeated retries and partial transfers require explicit treatment before estimating viewing. Neither a .ts suffix nor an HTTP success code proves a full segment was played. Deduplication must distinguish retries from legitimate replay and avoid counting audio and alternative renditions as additional viewing. Durations should come from validated media metadata where available, and unsupported estimates must remain labelled as proxies. These are design recommendations, not claims that every current SmartVOD output already implements them.''')

evidence_rows=[
['Evidence / source','Interpretation and boundary'],
['Jannach & Jugovac (2019): research commentary','Business metrics need explicit evaluation; algorithm improvement does not establish commercial gain.'],
['Zielnicki et al. (2026): working paper','Separate underlying interest from targeting; model-specific findings and disclosed platform ties limit transfer.'],
['Netflix (n.d.); Chandrashekar et al. (2017): provider accounts','Discovery includes ranking and representation; these accounts are not independent causal validation.'],
['Han & Yamana (2017): survey abstract','Consider diversity and coverage alongside accuracy; this project does not reproduce their review.'],
['You et al. (2026): archived-survey reanalysis','Satisfaction and intention are measured constructs; request logs cannot substitute for their questionnaire.'],
['Pantos & May (2017): informational specification','Differentiate playlist and media activity; protocol definitions do not certify human attention.'],
]

synopsis=[('Project title',TITLE),('Programme','MBA ITM & Data Science'),('Business problem','Content teams need to distinguish genuine changes in audience interest from metadata changes, incomplete data and delivery activity. The study examines how analytics can support defensible content promotion and catalogue decisions.'),('Objectives','1. Examine the role of audience analytics in OTT content strategy.\n2. Evaluate engagement and content-performance measures and their limitations.\n3. Recommend a practical decision framework informed by the SmartVOD design context.'),('Extended abstract',abstract),('Methodology','Structured narrative review of seven purposively selected secondary sources. Selected full-text sections, abstracts and bibliographic records are combined with official platform and protocol material. No surveys, interviews or confidential viewer-log analysis are presented as research evidence.'),('Proposed contribution','A content decision framework covering title/category movers, contribution-to-change, audience segmentation, returning identifiers and measurement confidence. Outputs are recommendations, not empirically demonstrated business improvements.'),('Scope and limitations','VOD content strategy; no revenue forecast, exact playback-retention claims or operational identifiers. Confirm programme-specific synopsis approval and any institution-specific formatting before submission.'),('Report structure','Introduction; problem and objectives; literature review; methodology; proposed framework; analysis and interpretation; results and discussion; recommendations; limitations and conclusion; references.')]

def inline(txt):
    return escape(txt).replace('&lt;i&gt;','<i>').replace('&lt;/i&gt;','</i>').replace('\n','<br/>')

def word_runs(txt,bold=False):
    runs=[];italic=False
    for bit in re.split(r'(<i>|</i>|\n)',txt):
        if bit=='<i>': italic=True;continue
        if bit=='</i>': italic=False;continue
        if bit=='\n': runs.append('<w:r><w:br/></w:r>');continue
        if not bit:continue
        pr='<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/>'
        pr+=('<w:b/>' if bold else '')+('<w:i/>' if italic else '')
        runs.append('<w:r><w:rPr>'+pr+'</w:rPr><w:t xml:space="preserve">'+escape(bit)+'</w:t></w:r>')
    return ''.join(runs)

def word_paragraph(txt,kind='body'):
    prop='<w:jc w:val="center"/>' if kind=='title' else ''
    if kind in ('heading','caption'): prop+='<w:keepNext/><w:keepLines/>'
    if kind=='ref':prop+='<w:ind w:left="720" w:hanging="720"/>'
    return '<w:p><w:pPr><w:widowControl/><w:spacing w:line="480" w:lineRule="auto" w:after="120"/>'+prop+'</w:pPr>'+word_runs(txt,kind in ('title','heading'))+'</w:p>'

def docx(path,parts):
    ps=[]
    for kind,txt in parts:
        if kind=='break':ps.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>');continue
        if kind=='table':
            rows=[]
            for n,row in enumerate(txt):
                cells=''.join('<w:tc><w:tcPr><w:tcW w:w="'+str(2700 if j==0 else 6326)+'" w:type="dxa"/>'+('<w:tcBorders><w:bottom w:val="single" w:sz="4"/></w:tcBorders>' if n==0 else '')+'</w:tcPr>'+word_paragraph(value,'heading' if n==0 else 'body')+'</w:tc>' for j,value in enumerate(row))
                rows.append('<w:tr><w:trPr><w:cantSplit/>'+('<w:tblHeader/>' if n==0 else '')+'</w:trPr>'+cells+'</w:tr>')
            ps.append('<w:tbl><w:tblPr><w:tblW w:w="9026" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>'+''.join('<w:'+side+' w:val="single" w:sz="4" w:color="777777"/>' for side in ('top','bottom'))+'</w:tblBorders></w:tblPr><w:tblGrid><w:gridCol w:w="2700"/><w:gridCol w:w="6326"/></w:tblGrid>'+''.join(rows)+'</w:tbl>');continue
        for block in txt.split('\n\n'):
            ps.append(word_paragraph(block,kind))
    body=''.join(ps)+'<w:sectPr><w:footerReference w:type="default" r:id="footer1"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/_rels/document.xml.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="footer1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>')
        z.writestr('word/footer1.xml','<?xml version="1.0"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman"/><w:sz w:val="20"/></w:rPr><w:t>Working draft | </w:t></w:r><w:fldSimple w:instr="PAGE"/></w:p></w:ftr>')
        z.writestr('word/document.xml','<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'+body+'</w:body></w:document>')

def pdf(path,parts):
    for face,file in [('TNR','times.ttf'),('TNR-Bold','timesbd.ttf'),('TNR-Italic','timesi.ttf'),('TNR-BoldItalic','timesbi.ttf')]:
        if face not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(face,str(Path('C:/Windows/Fonts')/file)))
    pdfmetrics.registerFontFamily('TNR',normal='TNR',bold='TNR-Bold',italic='TNR-Italic',boldItalic='TNR-BoldItalic')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='body12',fontName='TNR',fontSize=12,leading=24,spaceAfter=6,alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle(name='head12',fontName='TNR-Bold',fontSize=12,leading=24,spaceBefore=12,spaceAfter=6,keepWithNext=True))
    styles.add(ParagraphStyle(name='title12',fontName='TNR-Bold',fontSize=12,leading=24,alignment=1,spaceAfter=16))
    styles.add(ParagraphStyle(name='ref12',parent=styles['body12'],leftIndent=36,firstLineIndent=-36,alignment=0))
    styles.add(ParagraphStyle(name='cell12',parent=styles['body12'],alignment=0))
    styles.add(ParagraphStyle(name='caption12',parent=styles['body12'],alignment=0,keepWithNext=True))
    flow=[]
    for k,t in parts:
        if k=='break':flow.append(PageBreak());continue
        if k=='table':
            data=[[Paragraph(inline(s),styles['cell12']) for s in row] for row in t]
            table=Table(data,colWidths=[135,316.276],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),0.5,colors.black),('LINEBELOW',(0,0),(-1,0),0.5,colors.black),('LINEBELOW',(0,-1),(-1,-1),0.5,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            flow.append(table);flow.append(Spacer(1,12));continue
        for block in t.split('\n\n'):
            flow.append(Paragraph(inline(block),styles['title12' if k=='title' else 'head12' if k=='heading' else 'ref12' if k=='ref' else 'caption12' if k=='caption' else 'body12']))
    def foot(c,d):
        c.setFont('TNR',10);c.drawString(72,35,'Working draft | MBA ITM & Data Science');c.drawRightString(d.pagesize[0]-72,35,str(d.page))
    SimpleDocTemplate(str(path),pagesize=(595.276,841.89),leftMargin=72,rightMargin=72,topMargin=72,bottomMargin=72).build(flow,onFirstPage=foot,onLaterPages=foot)

def formatted_reference(row):
    sid,citation,url,*_=row
    italics={
      'S1':['Measuring the business value of recommender systems'],
      'S2':['The value of personalized recommendations: Evidence from Netflix'],
      'S3':['How Netflix\u2019s recommendations system works'],
      'S4':['Artwork personalization at Netflix'],
      'S5':['IEICE Transactions on Information and Systems, E100.D'],
      'S6':['HTTP live streaming'],
      'S7':['PLOS One, 21'],
    }
    for span in italics[sid]:citation=citation.replace(span,'<i>'+span+'</i>')
    return citation+(' Retrieved from '+url if url not in citation and 'doi:' not in citation else '')

cover=[('title',TITLE),('body','Minor Project | MBA ITM & Data Science\nAudited working draft | 11 November 2026\nStudent name: [To be supplied]\nEnrollment number: [To be supplied]\nInstitution: [To be supplied]\nGuide: [To be supplied]'),('body','Secondary-research report for student review. Personal details, institutional requirements and a genuine plagiarism check remain pending.')]
report=cover+[('break',''),('heading','Abstract'),('body',abstract)]
for n,(h,t) in enumerate(sections):
    report.extend([('heading',h),('body',t)])
    if n==5:report.extend([('caption','Table 1\n<i>Proposed metric definitions and analytical methods</i>'),('table',metric_rows),('body','Note. Original proposed operational definitions. They are not empirical results or externally validated thresholds.')])
    if n==6:report.extend([('caption','Table 2\n<i>Secondary-evidence synthesis</i>'),('table',evidence_rows),('body','Note. Author-date citations identify the sources listed in References. Interpretations are the proposed synthesis; source methods and limitations remain distinct.')])
report.extend([('break',''),('heading','References')])
for row in sorted(refs,key=lambda x:x[1]): report.append(('ref',formatted_reference(row)))
syn=[('title','Project Synopsis / Extended Abstract')]
for h,t in synopsis:syn.extend([('heading',h),('body',t)])
syn.append(('heading','Selected references'))
for row in sorted(refs,key=lambda x:x[1]):syn.append(('ref',formatted_reference(row)))
for name,parts in [('01_Project_Synopsis_DRAFT',syn),('02_Project_Report_DRAFT',report)]:
    docx(OUT/(name+'.docx'),parts);pdf(OUT/(name+'.pdf'),parts)
    flat=['\n'.join(' | '.join(row) for row in t) if k=='table' else re.sub('</?i>','',t) for k,t in parts if k!='break']
    (OUT/(name+'.txt')).write_text('\n\n'.join(flat),encoding='utf-8')
with (OUT/'03_Source_Register.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['ID','APA-style reference','URL','Material reviewed / evidence level','Use and limitation','Verified on']);w.writerows([list(r)+['2026-11-11'] for r in refs])
def word_count(txt):return len(re.findall(r"\b[\w'-]+\b",txt))
words=word_count(abstract+' '+' '.join(t for _,t in sections))
table_words=word_count(' '.join(s for table in (metric_rows,evidence_rows) for row in table for s in row))
notes=f'''PROJECT WORKSPACE - 11 November 2026
Programme: MBA ITM & Data Science
Title: {TITLE}
Report prose and abstract word count: {words}; excludes cover and references.
Prose + abstract + table cells: {words+table_words}; excludes captions and references.

FILES
01: Synopsis / extended abstract, editable Word and PDF.
02: Full working report, editable Word and PDF; text copy for review.
03: Source register with verification dates and evidence limitations.
04: Submission checklist and outstanding details (this file).
05: Audit findings and verification results.
_history: Original pre-audit drafts preserved for review.

COMPLETED
Guidelines reviewed; 12-word title reconciles both title instructions.
Secondary research method; seven checked sources and explicit evidence limitations.
All prescribed report sections; author-date citations; references; 12 pt font,
double spacing and 1-inch margins in the generated Word and PDF files.
Recent source plus foundational literature; no fabricated operational results.

BEFORE SUBMISSION
Supply student name, enrollment, institution and guide.
Confirm the institution's specialization wording and any required cover template.
Read and revise the report in your own understanding; inspect the original sources.
Expand the review if your guide requires more sources or a different research method.
Confirm whether a separate synopsis approval step is required by your institution.
Run an actual plagiarism checker and retain its report. No certificate or score
has been fabricated; the supplied guidelines require at least 85% originality.
Upload extended abstract, final report and genuine plagiarism report.
Answer the five actual viva questions after they become available on the portal.
No upload, viva submission or institutional approval has been performed.

METHOD NOTE
This is a structured narrative review, not a systematic review or an empirical
SmartVOD case study. Internal user identifiers, confidential logs and unverified
dashboard numbers have not been included. Business recommendations are proposals.
'''
(OUT/'04_Submission_Checklist.txt').write_text(notes,encoding='utf-8')
assert 2000<=words<=3500,words
assert 2000<=words+table_words<=3500,(words,table_words)
assert len(TITLE.split())==12
for file in OUT.glob('*.docx'):
    with zipfile.ZipFile(file) as z:
        import xml.etree.ElementTree as ET
        for n in z.namelist(): ET.fromstring(z.read(n))
import pymupdf
for file in OUT.glob('*.pdf'):
    d=pymupdf.open(file); assert len(d)>0; assert all(p.get_text().strip() for p in d)
    print(file.name,'pages',len(d))
print(json.dumps({'report_words_excluding_cover_references':words,'files':[f.name for f in OUT.iterdir()]},indent=2))
