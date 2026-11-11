from pathlib import Path
import json,re,zipfile,xml.etree.ElementTree as ET
import pymupdf
from PIL import Image,ImageDraw

root=Path(r'D:\sam\OTT_Audience_Analytics_Minor_Project\History\Quality_Upgrade_20261111')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
checks=[]
def check(label,condition,detail=''):
    checks.append({'check':label,'passed':bool(condition),'detail':detail})
    if not condition:raise AssertionError((label,detail))
count=lambda t:len(re.findall(r"\b[\w'-]+\b",t))
for stem in ('Project_Synopsis','Project_Report'):
    with zipfile.ZipFile(root/(stem+'.docx')) as z:
        for n in z.namelist():
            if n.endswith(('.xml','.rels')):ET.fromstring(z.read(n))
        x=ET.fromstring(z.read('word/document.xml'))
        check(stem+': no draft labels',b'Working draft' not in z.read('word/footer1.xml') and b'To be supplied' not in z.read('word/document.xml'))
        pg=x.find('.//w:pgMar',ns)
        check(stem+': one-inch margins',all(pg.get('{'+ns['w']+'}'+s)=='1440' for s in ('top','right','bottom','left')))
        runs=[r for r in x.findall('.//w:r',ns) if r.find('w:t',ns) is not None]
        check(stem+': Times New Roman 12 throughout',all(r.find('w:rPr/w:rFonts',ns).get('{'+ns['w']+'}ascii')=='Times New Roman' and r.find('w:rPr/w:sz',ns).get('{'+ns['w']+'}val')=='24' for r in runs))
        ps=[p for p in x.findall('.//w:p',ns) if p.find('.//w:t',ns) is not None]
        check(stem+': double spacing',all(p.find('w:pPr/w:spacing',ns).get('{'+ns['w']+'}line')=='480' for p in ps))
        check(stem+': eight hanging-indent references',len(x.findall('.//w:ind',ns))==8)
        check(stem+': reference italics',len(x.findall('.//w:i',ns))>=8)
        if stem=='Project_Report':
            tables=x.findall('.//w:tbl',ns)
            check('Report: two tables',len(tables)==2)
            check('Report: table grids match actual columns',all(all(len(row.findall('w:tc',ns))==len(tbl.findall('w:tblGrid/w:gridCol',ns)) for row in tbl.findall('w:tr',ns)) for tbl in tables))
            check('Report: embedded framework image','word/media/framework.png' in z.namelist())
            check('Report: image relationship exists',b'figure1' in z.read('word/_rels/document.xml.rels'))
            body_elements=list(x.find('w:body',ns))
            figure_index=next(i for i,e in enumerate(body_elements) if e.find('.//w:drawing',ns) is not None)
            figure_caption=body_elements[figure_index+1]
            check('APA6: figure caption below diagram',''.join(figure_caption.itertext()).startswith('Figure 1.'))
            caption_first_run=figure_caption.find('w:r',ns)
            check('APA6: figure label italic',caption_first_run.find('w:rPr/w:i',ns) is not None and caption_first_run.find('w:t',ns).text=='Figure 1.')
        else:
            heads=[''.join(p.itertext()) for p in ps if p.find('w:pPr/w:keepNext',ns) is not None]
            check('Synopsis: exact nine requested fields',heads==['Project Title','Project Area (Specialization/Stream)','Abstract','Why this topic has been chosen','Project Objective','Scope of the Project','Contribution of this Project','Methodology','References'])
    plain=(root/(stem+'.txt')).read_text(encoding='utf-8')
    body=plain.split('\n\nReferences')[0]
    for surname in ('Chandrashekar','Jannach','Mondal','Netflix','Pantos','Pereira','You','Zielnicki'):
        check(stem+': in-text citation '+surname,surname in body)
    check(stem+': no obsolete seven-source claim','seven sources' not in plain.lower() and 'Han & Yamana' not in plain)
    pdf=pymupdf.open(root/(stem+'.pdf'))
    check(stem+': readable PDF pages',all(p.get_text().strip() for p in pdf),len(pdf))
    outside=[];badfonts=[]
    for page in pdf:
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if not span['text'].strip():continue
                    if 'TimesNewRoman' not in span['font']:badfonts.append(span['font'])
                    x0,y0,x1,y1=span['bbox']
                    if y0>60 and y1<page.rect.height-55 and (x0<70 or x1>page.rect.width-70):outside.append((page.number+1,span['text']))
    check(stem+': rendered font is Times New Roman',not badfonts,badfonts)
    check(stem+': no text exceeds horizontal margins',not outside,outside)

report=(root/'Project_Report.txt').read_text(encoding='utf-8')
check('Complete report including references/tables/captions: 2000-3500 words',2000<=count(report)<=3500,count(report))
check('Report before references: at least 2000 words',count(report.split('\n\nReferences')[0])>=2000,count(report.split('\n\nReferences')[0]))
for h in ['Abstract','1. Introduction and business problem','2. Objectives, research questions and scope','3. Critical literature review','4. Research methodology','5. Data analysis and interpretation','6. Proposed content-decision framework','7. Results and discussion','8. Recommendations and implementation','9. Limitations and conclusion','References']:
    check('Required component: '+h,h in report)
check('Published index calculations',[100*(1+v/100) for v in (0,-4,-12,-16)]==[100,96,88,84])
check('Hypothetical contribution arithmetic',(150-200)==-50 and -50/200*100==-25 and -50/-80*100==62.5 and -80-(-50)==-30)
check('Hypothetical example explicitly labelled','Illustrative title calculation, not research findings' in report)
check('Nonreturners retained in cohort denominator','remain in the denominator as nonreturners' in report)

d=pymupdf.open(root/'Project_Report.pdf');thumbs=[]
for page in d:
    pix=page.get_pixmap(matrix=pymupdf.Matrix(.4,.4),alpha=False)
    thumbs.append(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
tw=max(im.width for im in thumbs)+14;th=max(im.height for im in thumbs)+26
sheet=Image.new('RGB',(tw*3,th*((len(thumbs)+2)//3)),'#d9d9d9');draw=ImageDraw.Draw(sheet)
for i,im in enumerate(thumbs):
    x=i%3*tw+7;y=i//3*th+19;sheet.paste(im,(x,y));draw.text((x,y-14),'Page '+str(i+1),fill='black')
sheet.save(root/'Report_Page_Overview.png')
result={'date':'2026-11-11','checks_passed':len(checks),'complete_report_words':count(report),'report_words_before_references':count(report.split('\n\nReferences')[0]),'report_pages':len(d),'native_word_opening':'Not verified; independent PDF rendering and OOXML checks completed.','checks':checks}
(root/'Quality_Audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
checklist=f'''FINAL QUALITY REVIEW - 11 November 2026
Complete report: {count(report)} words, including cover text, tables, captions and references.
Before references: {count(report.split(chr(10)+chr(10)+'References')[0])} words.
Sources: eight, with selected full-text research and source limitations recorded.
{len(checks)} structural, content, arithmetic and rendered-PDF checks passed.

IMPROVEMENTS
Independent Indian and Portuguese VOD research; thematic critical comparison.
Published-data worked example, calculated indices and clearly hypothetical title case.
Original framework figure; owned actions, triggers and evaluation criteria.
Explicit links between objectives, findings and recommendations.
Correct returning-cohort denominator; no invented business results or originality score.
Updated nine-field synopsis; separate full report supplied as required by the guide.

REMAINING SUBMISSION ITEMS
Add institution-required personal details/cover if requested by the portal or guide.
Read the sources and rehearse the practice viva in your own understanding.
Obtain a genuine plagiarism report meeting the supplied 85%-originality requirement.
Upload synopsis, full report and genuine plagiarism report; answer actual portal viva.
Institutional approval and marks are not guaranteed or claimed.
Native Word opening was not verified; PDF typography and Word structure were checked.
'''
(root/'Submission_Checklist.txt').write_text(checklist,encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
