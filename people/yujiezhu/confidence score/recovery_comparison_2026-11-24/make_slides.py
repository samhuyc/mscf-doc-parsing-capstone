"""Render exactly two update slides from comparison.json; no network access.

Run with ../.venv/bin/python make_slides.py after build_comparison.py.
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent
W, H = 1280, 720
NAVY, GREEN, AMBER = map(HexColor, ['#172C3E', '#087F75', '#A9680B'])
MUTED, BG, LINE = map(HexColor, ['#576B7B', '#F3F6F8', '#DCE5EB'])


def main():
    data = json.loads((ROOT/'comparison.json').read_text())
    summary, rows = data['summary'], data['samples']
    pdf = canvas.Canvas(str(ROOT/'UPDATE_SLIDES.pdf'), pagesize=(W,H))
    pdf.setTitle('Recovery comparison — 24 November 2026')
    pdf.setAuthor('Yujie Zhu · assistant-prepared source review')

    def text(x,y,s,size=20,color=NAVY,bold=False):
        pdf.setFillColor(color)
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
        assert pdf.stringWidth(s, 'Helvetica-Bold' if bold else 'Helvetica', size) <= W-x-35, s
        pdf.drawString(x,y,s)

    def para(s,x,y,width,size=20,color=NAVY,max_height=100):
        style=ParagraphStyle('p',fontName='Helvetica',fontSize=size,leading=size*1.28,textColor=color)
        p=Paragraph(s,style);_,height=p.wrap(width,max_height)
        assert height <= max_height,(s,height,max_height)
        p.drawOn(pdf,x,y-height)

    def card(x,y,w,h):
        pdf.setFillColor(white);pdf.roundRect(x,y,w,h,10,fill=1,stroke=0)

    def begin(title,page):
        pdf.setFillColor(BG);pdf.rect(0,0,W,H,fill=1,stroke=0)
        pdf.setFillColor(GREEN);pdf.rect(0,H-8,W,8,fill=1,stroke=0)
        text(48,674,'RECOVERY EXPERIMENT  |  24 NOVEMBER 2026',12,MUTED,True)
        text(48,623,title,34,NAVY,True)
        pdf.setStrokeColor(LINE);pdf.line(48,44,1232,44)
        text(48,23,'Saved-output replay | Selected cases | Assistant-reviewed; no independent human verification',11,MUTED)
        text(1198,23,f'{page:02}',12,MUTED)

    def crop(filename,box,x,y,width,height):
        with Image.open(ROOT/'assets'/filename) as im:
            region=im.crop(box)
            from reportlab.lib.utils import ImageReader
            pdf.drawImage(ImageReader(region),x,y,width=width,height=height,preserveAspectRatio=True,anchor='c',mask='auto')

    begin('Alternative parsing recovers 3 of 6 selected errors',1)
    para('MinerU OCR → PyMuPDF4LLM · 8 records from the existing 50-record pilot · no new model',48,591,1180,21,max_height=40)
    for x,big,label in [(48,f"{summary['original_correct']}/8 → {summary['retry_correct']}/8",'fully correct records'),
                         (448,str(summary['corrected']),'errors fully corrected'),
                         (848,str(summary['new_errors']),'new errors in 2 correct controls')]:
        card(x,458,384,100);text(x+20,510,big,35,GREEN,True);text(x+20,479,label,17,MUTED)
    xs=[64,577,738,883,1011]
    labels=['Sample','Assoc. score*','Original OK?','Retry OK?','Result']
    pdf.setFillColor(HexColor('#E5EDF2'));pdf.rect(48,412,1184,32,fill=1,stroke=0)
    for x,label in zip(xs,labels):text(x,423,label,15,NAVY,True)
    for i,row in enumerate(rows):
        y=383-i*32
        if i%2==0:
            pdf.setFillColor(white);pdf.rect(48,y-9,1184,32,fill=1,stroke=0)
        text(xs[0],y,f"{row['id']}  {row['short_name']}",16)
        text(xs[1],y,f"{row['association_score']:.4f} / {row['score_band']}",15)
        text(xs[2],y,'Yes' if row['original_correct'] else 'No',16)
        text(xs[3],y,'Yes' if row['retry_correct'] else 'No',16,GREEN if row['retry_correct'] else AMBER,True)
        text(xs[4],y,{'corrected':'Corrected','retained':'Retained','partial; still fails strict contract':'Partial only'}[row['outcome']],16)
    para('*Existing uncalibrated association output; not a probability. Low &lt; 0.5, high ≥ 0.5.',48,126,1180,17,AMBER,max_height=27)
    para('No low-score fully-correct cases exist in the 50-record pool; G–H are high-score correct controls.<br/>“Correct” requires numeric content + separate row/column binding + usable units.',48,94,1180,16,MUTED,max_height=45)
    pdf.showPage()

    begin('Correct digits do not guarantee correct context',2)
    card(48,232,580,357);card(650,232,582,357)
    text(68,554,'FULL RECOVERY  |  ROLLS-ROYCE',19,GREEN,True)
    crop('rolls_royce_2026h1_release_013.png',(48,177,843,277),68,431,540,96)
    para('<b>Revenue 11,448; cost of sales (8,021)</b><br/>Original digits were correct; the header merged 2026 and 2025. Alternative output binds both to 2026 (£m).',68,417,538,20,max_height=112)
    para('<b>Association score: 0.8837, yet wrong.</b><br/>These are high-score association errors;<br/>the digits were correct.',68,303,538,17.5,AMBER,max_height=70)
    text(670,554,'PARTIAL RECOVERY  |  EDF',19,AMBER,True)
    crop('edf_2024_003.png',(48,200,866,333),670,431,542,96)
    para('<b>3,037.10.0 → 3,037.1 &lt;br/&gt; 0.0</b><br/>The two numbers become readable. Revenue-from-sales and other-revenues still share one HTML cell.',670,417,538,20,max_height=112)
    para('<b>3 EDF records still fail the contract.</b><br/>Manually separating their rows would be another repair step; it is not counted here.',670,303,538,17.5,AMBER,max_height=70)
    para('<b>Takeaway:</b> another parser can restore missing context, but a retry still needs validation.<br/>A low-score-only retry policy would miss the two high-score Rolls-Royce errors shown here.',48,208,1180,23,max_height=65)
    para('Historical full-document PyMuPDF4LLM times: EDF 4.0 s / 6 pages; Rolls-Royce 30.6 s / 52 pages.<br/>No fresh retry latency measured. Selected, correlated cases cannot establish a general recovery rate.',48,124,1180,18,MUTED,max_height=55)
    pdf.save()
    print('Wrote UPDATE_SLIDES.pdf (2 slides).')


if __name__ == '__main__':
    main()
