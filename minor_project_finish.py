from pathlib import Path
import ast,csv,json,re,zipfile
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pymupdf
import xml.etree.ElementTree as ET

root=Path(r'D:\sam\OTT_Audience_Analytics_Minor_Project')
support=root/'History'/'Supporting'
support.mkdir(parents=True,exist_ok=True)
library=Path(__file__).with_name('minor_project_build.py')
if not library.exists():
    library=next(root.glob('History/Previous_material_*/_build/minor_project_build.py'))
tree=ast.parse(library.read_text(encoding='utf-8'))
names={'inline','word_runs','word_paragraph','docx','pdf','formatted_reference'}
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
exec(compile(ast.Module(body=functions,type_ignores=[]),str(library),'exec'))

title='Role of Audience Analytics in Improving OTT Content Strategy and Viewer Engagement'
abstract='''This project examines how audience analytics can support content strategy and viewer engagement on over-the-top (OTT) video platforms. Content managers need to identify titles and categories that are gaining or losing interest, understand differences between audience segments and decide which content deserves promotion or further investigation. These decisions become difficult when requests, devices, estimated watch time and actual viewers are treated as equivalent measures.

The study uses a structured narrative review of seven academic, platform and technical sources. It examines content discovery, recommendation evaluation, catalogue diversity, user-experience research and streaming measurement. The review distinguishes business outcomes from activity measures and perceived satisfaction from observed delivery requests. It does not collect primary data or present confidential viewer logs as empirical research evidence.

The project proposes a content-centred decision framework informed by the SmartVOD design context. The framework combines stable content identity, complete comparison periods, title and category trends, contribution-to-change analysis, audience segmentation and returning-identifier cohorts. It also includes checks for missing data, delivery problems and concentrated or unusual activity. Its contribution is a practical connection between data science methods, information governance and managerial decisions. Estimated watch time is treated as a proxy, while exact playback retention and completion require additional validated data. The framework is intended to support evidence-based content review; its commercial effectiveness remains a matter for subsequent evaluation.'''

sections=[
('Project Title',title),
('Project Area (Specialization/Stream)','MBA ITM & Data Science\nFocus areas: Business Intelligence, Audience Analytics, Information Technology Management and OTT Content Strategy.'),
('Abstract',abstract),
('Why this topic has been chosen','''This topic has been chosen because practical work on SmartVOD has highlighted the need to connect technical analytics with clear content decisions. A dashboard may report a rise in requests or estimated watch hours without explaining whether that change reflects broader audience interest, a few unusually active identifiers, a delivery issue or a change in content labelling. The project addresses this gap between reporting activity and interpreting its business relevance.

The topic also connects directly with MBA ITM & Data Science. It applies descriptive analytics, comparative analysis, cohort analysis, database identity management and information governance to a managerial problem. Published work cautions that algorithmic performance does not automatically establish business value (Jannach & Jugovac, 2019). Research also supports considering catalogue diversity and coverage alongside popularity or predictive accuracy (Han & Yamana, 2017).

The study therefore offers an opportunity to examine how trustworthy evidence can guide promotion, discovery and catalogue review while avoiding unsupported conclusions about human attention, satisfaction or financial returns.'''),
('Project Objective','''The overall objective is to examine how audience analytics can support informed OTT content decisions and to propose a practical framework for interpreting content performance.

1. To examine the role of audience analytics in OTT content strategy, particularly title discovery, category performance and content promotion.

2. To evaluate the usefulness and limitations of content-performance and engagement measures, including estimated watch time, known audience identifiers, returning activity, segmentation and delivery outcomes.

3. To recommend a content-decision framework that combines reliable metric definitions, comparable reporting periods and interpretable analytical outputs for managers.'''),
('Scope of the Project','''The project focuses on video-on-demand titles and categories. It covers changes in content activity over complete and comparable periods, the titles contributing to category growth or decline, audience differences across available region and device segments, and repeat activity associated with known identifiers. It also considers stable content identity so that an editorial or SEO title change does not automatically split one asset into separate titles.

The study examines how discovery and presentation can influence the interpretation of performance. Netflix describes personalized title ranking, while its artwork account explains how a title is represented during discovery (Netflix, n.d.; Chandrashekar, Amat, Basilico, & Jebara, 2017).

The scope is a secondary-research synthesis and proposed decision framework. It excludes primary surveys, interviews, confidential-log empirical analysis, revenue forecasts and a newly trained recommendation model. Request counts are not treated as confirmed human views. Exact playback retention, buffering and completion are not claimed without suitable player events and validated content-duration data.'''),
('Contribution of this Project','''The principal contribution is a proposed framework that converts content-performance measures into a structured review process. It connects a business question with the required metric, comparison period, supporting evidence, confidence limitation and possible managerial action.

The proposed outputs include title and category movers, contribution-to-change analysis, reach-and-engagement comparisons, audience segmentation and returning-identifier cohorts. A trust layer would display collection freshness, unknown metadata and delivery or concentration concerns alongside the insight. This would help managers distinguish a promising content opportunity from a signal that first needs investigation.

The project also clarifies distinctions that matter for decisions: a device is not necessarily a person; returning activity is not exact playback retention; and a favourable activity trend is not proof of causal business improvement. Recent research using archived OTT survey responses measures satisfaction and usage intention through reported perceptions rather than delivery requests (You, Song, & Feng, 2026).

The contribution is conceptual and practical. It proposes how existing analytical capabilities can support content review; it does not claim that the framework has already increased engagement, reduced churn or produced a financial return.'''),
('Methodology','''The project follows a descriptive and analytical secondary-research approach using a structured narrative review. Seven sources were selected purposively for their relevance to OTT content discovery, recommendation value, catalogue evaluation, user experience or streaming measurement. Source verification was conducted on 11 November 2026 using academic publishers, author repositories, official platform documentation and the RFC publication record.

The evidence includes selected full-text sections of Jannach and Jugovac (2019), Zielnicki et al. (2026) and You et al. (2026); the publisher abstract and bibliographic details of Han and Yamana (2017); and relevant Netflix and HLS documentation. The sources differ in evidential strength: they include research commentary, a working paper, a peer-reviewed archived-survey analysis, a survey abstract, provider accounts and an informational protocol specification. These differences are retained when interpreting claims.

Material is organised into four themes: business-value measurement, content discovery and catalogue breadth, engagement interpretation, and metric reliability. Findings are compared across these themes and translated into the proposed decision framework. HLS playlist and media-segment definitions help establish why different delivery requests should not be counted interchangeably (Pantos & May, 2017).

No statistical analysis of internal viewer data is performed for this submission. Proposed period comparisons, contribution calculations and returning-identifier cohorts are design recommendations. The review is not exhaustive or systematic, and platform-specific findings are not assumed to transfer directly to SmartVOD. No new survey, interview, experiment or measured commercial uplift is claimed.'''),
]
source_file=root/'03_Source_Register.csv'
if not source_file.exists():source_file=next(root.glob('History/Previous_material_*/03_Source_Register.csv'))
with source_file.open(encoding='utf-8-sig',newline='') as f:
    sources=list(csv.DictReader(f))
parts=[]
for heading,content in sections:parts.extend([('heading',heading),('body',content)])
parts.append(('heading','References'))
for s in sorted(sources,key=lambda r:r['APA-style reference']):
    parts.append(('ref',formatted_reference((s['ID'],s['APA-style reference'],s['URL']))))

docx_path=support/'Project_Synopsis.docx'
pdf_path=support/'Project_Synopsis.pdf'
docx(docx_path,parts)
# Finished synopsis: no draft-status text or extra personal-detail fields.
with zipfile.ZipFile(docx_path) as z:entries={n:z.read(n) for n in z.namelist()}
entries['word/footer1.xml']=entries['word/footer1.xml'].replace(b'Working draft | ',b'Project Synopsis | ')
with zipfile.ZipFile(docx_path,'w',zipfile.ZIP_DEFLATED) as z:
    for n,data in entries.items():z.writestr(n,data)
# Reuse the audited PDF renderer with the finished footer wording.
pdf_node=next(n for n in functions if n.name=='pdf')
pdf_source=ast.get_source_segment(library.read_text(encoding='utf-8'),pdf_node)
exec(pdf_source.replace('Working draft | MBA ITM & Data Science','Project Synopsis | MBA ITM & Data Science'))
pdf(pdf_path,parts)
plain='\n\n'.join(re.sub('</?i>','',t) for _,t in parts)
(support/'Project_Synopsis.txt').write_text(plain,encoding='utf-8')

ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with zipfile.ZipFile(docx_path) as z:
    for n in z.namelist():ET.fromstring(z.read(n))
    xml=ET.fromstring(z.read('word/document.xml'))
    headings=[]
    for p in xml.findall('.//w:p',ns):
        if p.find('w:pPr/w:keepNext',ns) is not None:
            headings.append(''.join(p.itertext()))
    expected=[h for h,_ in sections]+['References']
    assert headings==expected,(headings,expected)
    assert len(xml.findall('.//w:ind',ns))==7
    assert len(xml.findall('.//w:i',ns))>=7
    assert len(title.split())==12
    assert 'DRAFT' not in plain and '[To be supplied]' not in plain
    assert b'Working draft' not in z.read('word/footer1.xml')
doc=pymupdf.open(pdf_path)
assert all(p.get_text().strip() for p in doc)
rendered=' '.join(p.get_text() for p in doc)
for h in expected:assert h in rendered,h
assert 'Working draft' not in rendered
bad=[]
for page in doc:
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                if not span['text'].strip():continue
                assert 'TimesNewRoman' in span['font'],span
                x0,y0,x1,y1=span['bbox']
                if y0>60 and y1<page.rect.height-55 and (x0<70 or x1>page.rect.width-70):bad.append(span['text'])
assert not bad,bad
doc[0].get_pixmap().save(support/'Project_Synopsis_Preview.png')
validation={'sections':headings,'references':len(sources),'title_words':len(title.split()),'words_excluding_references':len(re.findall(r"\b[\w'-]+\b",' '.join(t for _,t in sections))),'pdf_pages':len(doc),'format':'Times New Roman 12 pt; double spacing; one-inch margins','status':'Nine-section finished synopsis; no draft labels or personal-detail placeholders. Word structure and rendered PDF checked; native Word opening not verified.'}
(support/'Final_Synopsis_Validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
print(json.dumps(validation,indent=2))
