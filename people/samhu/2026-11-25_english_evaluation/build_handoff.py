"""Build the presenter guide and the identical stand-alone results page."""
import argparse
import csv
import tempfile
from datetime import datetime
from pathlib import Path
import reportlab
from pypdf import PdfReader,PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reproduce import HERE,MODELS,reconstruct,rows

NAVY='#133344'; TEAL='#075F66'; INK='#203743'; MUTED='#4D656C'; PALE='#E6F1EF'; RULE='#C5D5D5'; GOLD='#8A4D21'; CREAM='#FBF1E5'; WHITE='#FFFFFF'
GITHUB='https://github.com/samhuyc/mscf-doc-parsing-capstone/'
BASE='people/samhu/2026-11-25_english_evaluation/'
UP='11f2a5a8b4cabb1f88a54c788d92941dd329e375'
NAMES={'paddle_vl':'PaddleOCR-VL-1.6','glm':'GLM-OCR','mineru_vlm':'MinerU 2.5 Pro','monkey':'MonkeyOCR-pro-1.2B','pymupdf':'PyMuPDF4LLM + Tesseract'}
SCAN_URL='https://find-and-update.company-information.service.gov.uk/company/00030209/filing-history/MzQ4Mzc5NDM2N2FkaXF6a2N4/document?download=0&format=pdf'

fontdir=Path(reportlab.__file__).parent/'fonts'
for key,filename in [('Sans','Vera.ttf'),('Bold','VeraBd.ttf'),('Ital','VeraIt.ttf')]:
    pdfmetrics.registerFont(TTFont(key,str(fontdir/filename)))

class Page:
    def __init__(self,canvas,size):
        self.c=canvas;self.w,self.h=size;self.c.setPageSize(size)
    def text(self,x,y,value,size=11,font='Sans',color=INK,align='left'):
        c=self.c;c.setFont(font,size);c.setFillColor(HexColor(color))
        getattr(c,{'left':'drawString','right':'drawRightString','center':'drawCentredString'}[align])(x,self.h-y,str(value))
    def rect(self,x,t,w,h,fill):
        self.c.setFillColor(HexColor(fill));self.c.rect(x,self.h-t-h,w,h,fill=1,stroke=0)
    def rule(self,x,t,w,color=RULE,thickness=.7):
        self.c.setStrokeColor(HexColor(color));self.c.setLineWidth(thickness);self.c.line(x,self.h-t,x+w,self.h-t)
    def para(self,x,y,text,width,size=10.5,leading=15.8,color=INK,font='Sans'):
        for line in simpleSplit(text,font,size,width):
            self.text(x,y,line,size,font,color);y+=leading
        return y
    def link(self,x,y,label,url,size=9.3):
        self.text(x,y,label,size,'Bold',TEAL)
        width=pdfmetrics.stringWidth(label,'Bold',size)
        self.c.linkURL(url,(x,self.h-y-2,x+width,self.h-y+size+1),relative=0,thickness=0)
    def table(self,x,t,widths,headers,records,*,head=34,row=28,fs=10,align=None,bold=None):
        total=sum(widths);self.rect(x,t,total,head,NAVY)
        align=align or ['left']+['center']*(len(widths)-1)
        def item(c,t,h,v,w,a,font,color,size):
            cx=c+8 if a=='left' else c+w-8 if a=='right' else c+w/2
            lines=str(v).split('\n');yy=t+(h-(len(lines)-1)*(size+2))/2+size*.34
            for j,s in enumerate(lines):self.text(cx,yy+j*(size+2),s,size,font,color,a)
        c=x
        for w,label,a in zip(widths,headers,align):
            item(c,t,head,label,w,a,'Bold',WHITE,fs-.4);c+=w
        t+=head
        for i,record in enumerate(records):
            if i%2==0:self.rect(x,t,total,row,PALE if i==0 else '#F1F5F4')
            c=x
            for j,(w,v,a) in enumerate(zip(widths,record,align)):
                emph=(bold is not None and (i,j) in bold)
                item(c,t,row,v,w,a,'Bold' if emph else 'Sans',TEAL if emph else INK,fs);c+=w
            self.rule(x,t+row,total);t+=row
        return t
    def head(self,tag,title,sub=None):
        self.rect(0,0,self.w,6,TEAL);self.text(45,42,tag.upper(),10,'Bold',TEAL)
        self.text(43,84,title,27,'Bold',NAVY)
        if sub:self.para(45,112,sub,522,11.2,16)
    def foot(self,n):
        self.rule(45,750,522);self.text(45,769,'CMU MSCF   /   Barclays capstone     •     English filing evaluation',8.5,'Sans',MUTED)
        self.text(567,769,str(n)+' / 5',8.5,'Bold',MUTED,'right')
    def sec(self,x,y,s):self.text(x,y,s,14,'Bold',TEAL)

def stamp(d):
    return datetime.fromisoformat(d['release']['snapshot_et']).strftime('%d %b %Y, %I:%M %p ET').replace(' 0',' ')

def f3(v):return f'{v:.3f}'

def results(canvas,d):
    p=Page(canvas,(960,540));p.rect(0,0,960,7,TEAL)
    p.text(36,39,'CMU MSCF   /   BARCLAYS CAPSTONE',10.7,'Bold',TEAL)
    p.text(924,39,'PRELIMINARY   •   '+stamp(d),10,'Sans',MUTED,'right')
    p.text(34,79,'English financial statement parsing',30,'Bold',NAVY)
    ft=d['matched']['ft'];lead=max(MODELS,key=lambda m:ft['scores'][m]['fact_f1'])
    p.text(36,110,'Paddle leads on FinTabNet financial fact F1. MinerU recovers more checked values on UK scans.' if lead=='paddle_vl' else 'Crop recognition and whole-page parsing are measured on separate sets of identical inputs.',14,'Sans',INK)
    p.sec(36,153,'FinTabNet  /  Table recognition')
    p.text(36,175,f"{ft['n']} matched tables from {ft['issuers']} issuers. Scores range from 0 to 1.",10.9,'Sans',MUTED)
    models=sorted(MODELS,key=lambda m:-ft['scores'][m]['fact_f1'])
    records=[[NAMES[m],*(f3(ft['scores'][m][key]) for key in ('structure_teds','full_teds','fact_f1'))] for m in models]
    p.table(36,190,[177,87,83,97],['Parser','Structure\nTEDS','Full\nTEDS','Financial\nfact F1'],records,head=39,row=32,fs=11.7,bold={(0,3)})
    p.sec(512,153,'SEC and UK filings  /  Whole pages')
    p.text(512,175,'Identical filing inputs for the two end-to-end parsers.',10.9,'Sans',MUTED)
    fc=d['pages'];checks=d['checks']
    lines=[['Berkshire span recall',*(f"{fc[m]['critical_span_recall']:.1%}" for m in ('mineru_vlm','pymupdf'))],
           ['Berkshire context recall',*(f"{fc[m]['critical_context_recall']:.1%}" for m in ('mineru_vlm','pymupdf'))]]
    for key,title in [('ak','Apple 10-K values'),('aq','Apple 10-Q values'),('uk','UK scan values')]:
        lines.append([title,*(f"{checks[key][m]['value_matches']}/{checks[key][m]['values']}" for m in ('mineru_vlm','pymupdf'))])
    p.table(512,190,[194,99,119],['Check','MinerU\n2.5 Pro','PyMuPDF4LLM\n+ Tesseract'],lines,head=39,row=32,fs=11.4,bold={(4,1),(4,2)})
    nt=ft['timeouts']['mineru_vlm'];timeout=f"{nt} MinerU crop timeout{'s' if nt!=1 else ''} included at zero." if nt else 'Each completed crop receives one vote.'
    p.para(36,417,timeout+' Three recognizers received crops. Both page parsers received those crops in single-page PDFs.',444,10.2,14.2,MUTED)
    p.para(512,417,'Berkshire covers 12 excerpts and 690 labeled occurrences. Apple and UK counts cover values in selected rows. UK references span 3 scanned filings.',412,10.2,14.2,MUTED)
    p.rule(36,467,888)
    hist=d['michael'];numbers='  /  '.join(f"{n} {hist[NAMES[m]]['fact_f1']['value']:.3f}" for n,m in [('Paddle','paddle_vl'),('GLM','glm'),('Monkey','monkey')])
    p.text(36,491,'Larger FinTabNet check',11.2,'Bold',TEAL)
    p.text(216,491,'Michael’s 300-table run, financial fact F1 on 283 eligible tables',11.1,'Sans',INK)
    p.text(36,516,numbers,12,'Bold',NAVY);p.text(924,516,'Cohorts reported separately.',10.3,'Sans',MUTED,'right')
    canvas.showPage()

def page1(c,d):
    p=Page(c,letter);p.head('Presenter guide   /   Evaluation framework','What changed in the benchmark')
    p.para(45,116,'Eunice (Yuyang)  •  Prepared by Sam Hu  •  '+stamp(d),520,10.4,15,MUTED)
    p.rect(45,143,522,82,PALE)
    p.para(60,169,'The question for Barclays',482,12,17,TEAL,'Bold')
    p.para(60,192,'If a parser reads an amount correctly, can it also keep that amount under the correct year and beside the correct line item?',480,12.8,18,NAVY)
    p.sec(45,263,'From earlier work to this comparison')
    y=p.para(45,288,'Eunice’s PubTabNet work measured how closely a predicted table matched its reference tree. Sam’s earlier presentation examined how certain a parser was about its own output. This benchmark measures which parts of an English financial filing each parser recovered correctly.',520)
    p.para(45,y+7,'We scored the same saved output several ways. Cropped annual-report tables test structure and financial meaning. Annotated 10-Q excerpts test wording. Original US and UK PDFs test whether an amount stays in its printed row after a full-page parse.',520)
    p.sec(45,417,'What each teammate contributed')
    entries=[('Eunice / Yuyang','Full and structure-only TEDS. We applied her scorer to the same normalized table markup for every parser.'),
             ('Sam','Saved model outputs, row/header/value matching and the filing-page checks. He assembled and ran the English comparison.'),
             ('Yujie','A common input, reference and prediction format, with file hashes and separate metric families.'),
             ('Michael','A 300-table CPU run with saved per-table scores. It supplies a larger check on the crop results.'),
             ('Oli','Layout and metadata evaluation. Those outcomes can be measured separately when their own labels are available.')]
    y=435
    for i,(name,what) in enumerate(entries):
        if i%2==0:p.rect(45,y,522,43,'#F2F6F5')
        p.text(55,y+18,name,10.4,'Bold',NAVY)
        p.para(173,y+17,what,383,9.65,13);y+=45
    p.para(45,694,'Read pages 2 and 3 for the metrics. Page 4 is the one-page results exhibit. Page 5 gives a short speaking script and the sample limits.',522,10.2,15,MUTED)
    p.foot(1);c.showPage()

def page2(c,d):
    p=Page(c,letter);p.head('Table metrics','What makes a table correct?','Consider this two-cell example. The values are illustrative and are separate from the benchmark results.')
    p.table(45,153,[113,70,70],['Reference','2024','2025'],[['Revenue','100','120']],head=27,row=35,fs=10.3)
    p.table(313,153,[113,70,70],['Parser output','2024','2025'],[['Revenue','120','100']],head=27,row=35,fs=10.3)
    p.para(45,247,'The rows and columns line up. Both numbers appear. Yet both year-value pairs are wrong. If these were the only two facts, structure TEDS would be 1.00 and financial fact F1 would be 0.00.',522,11.2,16)
    p.sec(45,324,'Five scores for five questions')
    items=[('Structure-only TEDS','Did the parser rebuild the rows, cells and merged headers? It compares the table trees with the cell text removed. The swap above leaves this score unchanged.'),
           ('Full TEDS','Did the tree and the cell contents survive? Changing one digit can lower this score even if every row and column is in place.'),
           ('GriTS content','How much of the cell grid can be aligned? It gives partial credit for similar text. Most of a large grid can align while one material value is wrong.'),
           ('Financial fact F1','Does the same value belong to the same row and header path? Extra or wrongly assigned facts lower precision. Missing facts lower recall. F1 balances the two.'),
           ('Numeric-cell F1','Is the printed numeric token in the correct grid position, with the correct cell span? This can detect a year-column swap even when all digits appear somewhere.')]
    y=344
    for i,(k,tx) in enumerate(items):
        p.rule(45,y,522);p.text(45,y+20,k,11.3,'Bold',NAVY)
        p.para(213,y+18,tx,352,10.15,14.7);y+=63
    p.rect(45,674,522,55,PALE)
    p.para(58,696,'For the presentation, put full TEDS beside financial fact F1. TEDS describes how closely the table was rebuilt. Financial fact F1 tests whether its amounts are usable.',494,10.5,15,TEAL)
    p.foot(2);c.showPage()

def page3(c,d):
    p=Page(c,letter);p.head('Whole-page metrics','What survives a full-page parse?')
    p.sec(45,124,'FinCriticalED    /    Critical wording')
    p.para(45,149,'Twelve English excerpts from Berkshire Hathaway’s Q3 2025 Form 10-Q contain 690 annotated occurrences, including numbers, dates and financial terms. Each excerpt receives equal weight.',522,10.8,15.5)
    p.text(45,204,'Critical span recall',11.2,'Bold',NAVY)
    p.para(45,224,'Can the annotated string be found on the page? A field can get credit even when it appears far from its original sentence.',244,10.1,14.6)
    p.text(316,204,'Exact context recall',11.2,'Bold',NAVY)
    p.para(316,224,'Can the complete annotated row or paragraph be found? A missing word or a punctuation change can cost the whole context.',248,10.1,14.6)
    p.para(45,291,'Page edit distance measures character changes across the whole excerpt. Lower is better. Small page-wide differences can coexist with a consequential change to one amount.',522,10.5,15.2,MUTED)
    p.rule(45,340,522)
    p.sec(45,371,'Filed PDFs    /    Tie the number to its row')
    p.para(45,396,'For Apple and Companies House accounts, the scorer looks for the named row once, then checks the ordered values on that row. A value counts when its sign and decimals survive. A row passes only when every checked value matches.',522,10.7,15.5)
    p.rect(45,457,522,143,'#F0F4F3');p.text(59,480,'HARRODS LIMITED   /   CASH AT BANK AND IN HAND',9.6,'Bold',TEAL)
    p.text(59,500,'Balance sheet, FY2025 accounts. The printed columns are 2025 and 2024 (£m).',9.2,'Sans',MUTED)
    p.rect(57,513,498,39,WHITE)
    p.c.drawImage(str(HERE/'evidence/harrods_cash_line.png'),61,p.h-547,width=488,height=18,preserveAspectRatio=True,anchor='c',mask='auto')
    p.text(59,574,'MinerU   76.6 and 50.8  (2/2)',10.4,'Bold',TEAL)
    p.text(322,574,'PyMuPDF   76.6 and 508  (1/2)',10.1,'Bold',GOLD)
    p.link(45,624,'Open the original filing, PDF page 24 (printed page 22)',SCAN_URL)
    p.para(45,658,'The 19 original pages cover Apple’s annual and quarterly filings plus three UK companies. The 219 checked values are selected examples. A number appearing elsewhere on the page earns no credit for the selected row.',522,10.6,15.2)
    p.foot(3);c.showPage()

def page5(c,d):
    p=Page(c,letter);p.head('Presenter notes','How to explain the result')
    ft=d['matched']['ft'];scores=ft['scores'];pa=scores['paddle_vl']['fact_f1'];gl=scores['glm']['fact_f1']
    p.sec(45,128,'A 45-second walkthrough')
    text=(f'“We tested two distinct jobs. On the same {ft["n"]} English financial tables, Paddle scored {pa:.3f} on matching financial facts, compared with {gl:.3f} for GLM. That metric asks whether the amount stays with its line item and year. '
          'On the original Apple filings, both end-to-end parsers recovered all 119 checked values. On the UK scans, MinerU recovered 100 of 100 values in the correct rows. PyMuPDF with Tesseract recovered 76. We would therefore choose a parser with the document type and the extraction task in mind.”')
    p.rect(45,147,522,157,PALE);p.para(60,174,text,489,11.4,17,NAVY)
    p.sec(45,342,'What the larger runs add')
    hold=d['other_tables']['hold'];uk=d['other_tables']['ukcrop'];big=d['other_tables']['ft']
    p.table(45,361,[193,102,110,117],['Cohort','Paddle fact F1','GLM fact F1','Monkey fact F1'],
        [[label,*(f3(v[m]['metrics']['fact_f1']) for m in ('paddle_vl','glm','monkey'))] for label,v in [('56 development tables',big),('11 different-issuer tables',hold),('7 UK scanned table crops',uk)]],fs=9.3,head=30,row=25)
    p.para(45,497,'The 11 issuers are absent from the 56-table development set. Three of the 11 tables also appear in Michael’s 300-table archive. The seven UK crops come from Dyson and Harrods. In those seven crops, GLM has the highest financial fact F1 of the three archived recognizers.',522,10.5,15.3)
    p.sec(45,576,'If someone asks about confidence or sample size')
    p.para(45,601,'Confidence is the model’s own estimate or signal. Every accuracy number here compares a prediction with a reference. The Berkshire test covers one issuer. The filed-PDF checks cover selected rows. A parser-wide ranking would require more filings and independent review of the source transcriptions.',522,10.5,15.3)
    p.para(45,679,'The AI handoff has exact definitions, file paths and the audit trail. The one-page companion is the same exhibit as page 4.',522,10.2,14.5,MUTED)
    p.link(45,721,'Open the project evidence',GITHUB+'tree/main/'+BASE+'evidence')
    p.foot(5);c.showPage()

def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--output',type=Path,default=HERE);a=cli.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);d=reconstruct(HERE/'evidence')
    one=a.output/'Results_One_Page.pdf';c=Canvas(str(one),pagesize=(960,540),pageCompression=1)
    c.setTitle('English financial statement parsing • Results');c.setAuthor('CMU MSCF capstone team');results(c,d);c.save()
    with tempfile.TemporaryDirectory() as td:
        draft=Path(td)/'reader.pdf';c=Canvas(str(draft),pagesize=letter,pageCompression=1)
        for fn in (page1,page2,page3,page5):fn(c,d)
        c.save();reader=PdfReader(draft);slide=PdfReader(one);w=PdfWriter()
        for page in (reader.pages[0],reader.pages[1],reader.pages[2],slide.pages[0],reader.pages[3]):w.add_page(page)
        w.add_metadata({'/Title':'Evaluation framework • Presenter handoff','/Author':'CMU MSCF capstone team'})
        for i,title in enumerate(('What changed','Table metrics','Whole-page metrics','Results exhibit','Presenter notes')):w.add_outline_item(title,i)
        with (a.output/'Presenter_Guide.pdf').open('wb') as f:w.write(f)

if __name__=='__main__':main()
