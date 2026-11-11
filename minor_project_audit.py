from pathlib import Path
import json,re,zipfile,unicodedata,xml.etree.ElementTree as ET
import pymupdf
from PIL import Image,ImageDraw

root=Path(r'D:\sam\OTT_Audience_Analytics_Minor_Project')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
checks=[]
def check(name,ok,detail=''):
    checks.append({'check':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError((name,detail))

check('Original pre-audit drafts preserved',(root/'_history/before_audit_20261111/02_Project_Report_DRAFT.docx').exists())
checklist=(root/'04_Submission_Checklist.txt').read_text(encoding='utf-8')
counts=[int(s) for s in re.findall(r'word count: (\d+)',checklist)]
check('Report prose length within required range',len(counts)==1 and 2000<=counts[0]<=3500,counts)
total=int(re.search(r'Prose \+ abstract \+ table cells: (\d+)',checklist).group(1))
check('Report including tables within word limit',2000<=total<=3500,total)

for stem in ('01_Project_Synopsis_DRAFT','02_Project_Report_DRAFT'):
    with zipfile.ZipFile(root/(stem+'.docx')) as z:
        for member in z.namelist():ET.fromstring(z.read(member))
        xml=ET.fromstring(z.read('word/document.xml'))
        margins=xml.find('.//w:pgMar',ns)
        check(stem+': one-inch margins',all(margins.get('{'+ns['w']+'}'+s)=='1440' for s in ('top','right','bottom','left')))
        paragraphs=xml.findall('.//w:p',ns)
        texts=[''.join(p.itertext()) for p in paragraphs]
        check(stem+': 12-word title',any(len(t.split())==12 and t.startswith('Role of Audience Analytics') for t in texts))
        check(stem+': real Word line breaks',len(xml.findall('.//w:br',ns))>=2)
        text_runs=[r for r in xml.findall('.//w:r',ns) if r.find('w:t',ns) is not None]
        check(stem+': every text run specifies Times New Roman 12',all(r.find('w:rPr/w:rFonts',ns).get('{'+ns['w']+'}ascii')=='Times New Roman' and r.find('w:rPr/w:sz',ns).get('{'+ns['w']+'}val')=='24' for r in text_runs))
        text_ps=[p for p in paragraphs if p.find('.//w:t',ns) is not None]
        check(stem+': double spacing',all(p.find('w:pPr/w:spacing',ns).get('{'+ns['w']+'}line')=='480' for p in text_ps))
        check(stem+': italic reference titles',len(xml.findall('.//w:i',ns))>=7)
        check(stem+': reference hanging indents',len(xml.findall('.//w:ind',ns))==7)
        if stem.startswith('02'):
            check('Report has two actual Word tables',len(xml.findall('.//w:tbl',ns))==2)
            check('Explicit results and discussion section',any(t=='7. Results and discussion' for t in texts))
            check('Cover and reference page breaks',len(xml.findall('.//w:br[@w:type="page"]',ns))==2)
    pdf=pymupdf.open(root/(stem+'.pdf'))
    check(stem+': readable nonempty PDF pages',all(len(p.get_text().strip())>15 for p in pdf),len(pdf))
    badfont=[];outside=[]
    for page in pdf:
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if not span['text'].strip():continue
                    if 'TimesNewRoman' not in span['font']:badfont.append((page.number+1,span['font'],span['text'][:30]))
                    x0,y0,x1,y1=span['bbox']
                    if y0>60 and y1<page.rect.height-55 and (x0<70 or x1>page.rect.width-70):outside.append((page.number+1,span['text'][:35],span['bbox']))
    check(stem+': rendered text uses actual Times New Roman',not badfont,badfont)
    check(stem+': no body text crosses horizontal margins',not outside,outside)
    txt=' '.join(p.get_text() for p in pdf)
    for phrase in ('You','Zielnicki','Jannach','Han','Netflix','Pantos','Chandrashekar'):
        check(stem+': reference present '+phrase,phrase in txt)

report=pymupdf.open(root/'02_Project_Report_DRAFT.pdf')
report[0].get_pixmap(matrix=pymupdf.Matrix(1,1)).save(root/'report_preview.png')
scale=.38;thumbs=[]
for p in report:
    pix=p.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
    thumb=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    thumbs.append(thumb)
tw=max(im.width for im in thumbs)+14;th=max(im.height for im in thumbs)+28
sheet=Image.new('RGB',(tw*3,th*((len(thumbs)+2)//3)),'#d8d8d8');draw=ImageDraw.Draw(sheet)
for i,im in enumerate(thumbs):
    x=(i%3)*tw+7;y=(i//3)*th+20;sheet.paste(im,(x,y));draw.text((x,y-15),f'Page {i+1}',fill='black')
sheet.save(root/'audit_page_overview.png')
result={'date_ist':'2026-11-11','checks_passed':len(checks),'checks':checks,'prose_abstract_words':counts[0],'prose_abstract_table_words':total,'report_pdf_pages':len(report),'word_validation':'Word package structure checked. Desktop Word automation did not respond and was closed; an actual Word desktop opening has not been verified. PDFs were rendered independently and inspected.'}
(root/'audit_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
notes=f'''AUDIT - 11 November 2026
Outcome: substantive and formatting revisions completed; {len(checks)} automated checks passed.

CORRECTIONS
- Title changed to exactly 12 words to meet both wording limits in the guide.
- PDF now embeds actual Times New Roman; Word uses actual line/page breaks.
- References alphabetised with italic styling and hanging indents in both formats.
- A recent independent peer-reviewed OTT study added; seven sources in total.
- Selected full-text academic sections checked; evidence depth recorded honestly.
- Explicit results/discussion ties the synthesis to the three study objectives.
- Metric definitions and evidence tables added; prior-semester analytics links explained.
- Partial transfers/retries and known-ID denominators clarified; proposals distinguished
  from currently implemented features and from empirical findings.
- Original drafts retained under _history/before_audit_20261111.

VERIFICATION
Prose and abstract: {counts[0]} words.
Prose, abstract and table cells: {total} words; below 3,500 even before exclusions.
Report PDF: {len(report)} pages. Word OOXML, margins, font, spacing, tables,
reference styling, rendered PDF fonts and horizontal bounds checked.
Page overview and preview generated for visual inspection.
Desktop Word automation did not respond and its audit-only helper was closed.
The DOCX package passed structural checks; native Word opening remains unverified.
PDF files were independently rendered with the actual Times New Roman fonts.

REMAINING USER / INSTITUTION ITEMS
Student name, enrollment number, institution and guide; student review;
institution-specific approval/template; genuine plagiarism report; actual portal viva.
No originality percentage or empirical business improvement is claimed.
'''
(root/'05_Audit_Report.txt').write_text(notes,encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
