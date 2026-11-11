"""Make a portable eight-slide PDF from the computed pilot, without network access."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent
W, H = 1280, 720
NAVY = HexColor('#172C3E')
MUTED = HexColor('#576B7B')
GREEN = HexColor('#087F75')
AMBER = HexColor('#A9680B')
BG = HexColor('#F3F6F8')
LINE = HexColor('#DCE5EB')


def main():
    summary = json.loads((ROOT/'summary.json').read_text())
    high, low = [summary['groups'][k] for k in ['stronger','weaker']]
    pdf = canvas.Canvas(str(ROOT/'CONFIDENCE_DEMO.pdf'), pagesize=(W,H), pageCompression=1)
    pdf.setTitle('Extraction evidence — corrected sponsor pilot')
    pdf.setAuthor('Yujie Zhu · assistant-prepared pilot')
    pdf.setSubject('Observed evidence and a plan for validated correctness probabilities')
    page = 0

    def text(x,y,value,size=20,color=NAVY,bold=False):
        pdf.setFillColor(color)
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
        pdf.drawString(x,y,value)

    def para(value,x,y,width,size=23,color=NAVY,max_height=200):
        style=ParagraphStyle('body',fontName='Helvetica',fontSize=size,leading=size*1.32,textColor=color)
        p=Paragraph(value,style)
        _,height=p.wrap(width,max_height)
        assert height <= max_height, (value,height,max_height)
        p.drawOn(pdf,x,y-height)
        return y-height

    def card(x,y,width,height,color=white):
        pdf.setFillColor(color)
        pdf.roundRect(x,y,width,height,12,fill=1,stroke=0)

    def begin(title,kicker='CONFIDENCE IN FINANCIAL EXTRACTION'):
        nonlocal page
        if page:
            pdf.showPage()
        page+=1
        pdf.setFillColor(BG); pdf.rect(0,0,W,H,fill=1,stroke=0)
        pdf.setFillColor(GREEN); pdf.rect(0,H-9,W,9,fill=1,stroke=0)
        text(56,665,kicker,13,MUTED,True)
        text(56,607,title,37,NAVY,True)
        pdf.setStrokeColor(LINE); pdf.line(56,53,1224,53)
        text(56,29,'10 NOV 2026  |  PRELIMINARY PILOT  |  ASSISTANT-REVIEWED SOURCE RENDERS',11,MUTED)
        text(1190,29,f'{page:02}',13,MUTED)

    def source(filename,box,x,y,width,height):
        path=ROOT/'assets'/filename
        with Image.open(path) as img:
            iw,ih=img.size
        left,top,right,bottom=box
        scale=min(width/(right-left),height/(bottom-top))
        dw,dh=(right-left)*scale,(bottom-top)*scale
        x+=(width-dw)/2; y+=(height-dh)/2
        pdf.saveState()
        p=pdf.beginPath(); p.rect(x,y,dw,dh); pdf.clipPath(p,stroke=0,fill=0)
        pdf.drawImage(ImageReader(str(path)),x-left*scale,y-(ih-bottom)*scale,
                      width=iw*scale,height=ih*scale,mask='auto')
        pdf.restoreState()

    begin('Extraction evidence before probability calibration')
    para('A working diagnostic prototype using saved sponsor-document outputs.',56,560,1150,27)
    for x,group,label,color in [(56,high,'STRONGER EVIDENCE',GREEN),(653,low,'WEAKER EVIDENCE',AMBER)]:
        card(x,245,571,230)
        text(x+28,435,label,15,color,True)
        text(x+28,351,f"{group['correct']}/{group['n']}",68,color,True)
        para(f"Observed development cells passing the strict contract.<br/>{len(group['documents'])} development document(s).",x+28,316,515,21)
    para('<b>Probability for a new cell: not yet estimated.</b>',56,207,1160,28)
    para('These counts describe this sample. They are not individual correctness probabilities.',56,137,1150,23,AMBER)

    begin('Numeric correctness and association are different')
    card(56,300,564,240); card(644,300,580,240)
    text(80,490,'NUMERIC TRANSCRIPTION',21,GREEN,True)
    para('Are the digits, decimal and sign right?<br/><br/>45/50 sampled cells preserve numeric content.',80,451,512,27)
    text(669,490,'STRUCTURED FINANCIAL CELL',21,GREEN,True)
    para('Are the value, row, column and unit context usable?<br/><br/>30/50 pass this stricter contract.',669,451,527,27)
    para('A merged year header can fail the second test while the number itself is correct.',56,240,1160,27)
    para('These are assistant-reviewed sample counts. Independent human verification is still needed.',56,141,1160,22,AMBER)

    begin('Observable evidence can flag problems')
    for i,(title,body) in enumerate([
        ('VALUE','One well-formed numeric token in an unmerged value cell.'),
        ('ROW','An unmerged label and one matching comparison row.'),
        ('AGREEMENT','Matching values and individually bound column headers.')]):
        x=56+i*394; card(x,290,374,250)
        text(x+22,494,title,20,GREEN,True); para(body,x+22,452,330,27)
    para('All checks pass: stronger evidence. Otherwise: weaker evidence.',56,240,1160,27)
    para('These categories do not quantify probability. Unit correctness is reviewed but has no separate prediction feature here.',56,156,1160,23,AMBER)

    begin('CVS: correct value with supporting evidence','SOURCE EXAMPLE | CVS, PHYSICAL PAGE 6')
    card(56,160,745,403); source('cvs_2025q2_006.png',(68,140,899,589),70,180,715,355)
    card(823,160,401,403); text(849,510,'STRONGER EVIDENCE',19,GREEN,True)
    para('<b>Total Revenues</b><br/>$98.9 billion<br/>2Q 2025',849,460,342,27)
    para('Both parsers agree. Source review confirms value and context.',849,331,342,23)
    para('<b>Probability:</b><br/>not estimated',849,236,342,23,AMBER)
    para('A reviewed correct example illustrates the checks; it does not establish a new-cell probability.',56,122,1160,19,MUTED)

    begin('EDF: flag the reason for uncertainty','SOURCE EXAMPLE | EDF, PHYSICAL PAGE 3')
    card(56,303,1168,260); source('edf_2024_003.png',(48,198,868,359),72,317,1135,222)
    card(56,103,768,176)
    para('<b>Merged row label:</b> Total revenueRevenue from sale of electricity and gasOther revenues',78,257,721,21,max_height=85)
    para('<b>Returned values:</b> 3,037.1, then 3,037.10.0<br/>A correct number can lack usable financial context.',78,184,721,20,max_height=75)
    card(846,103,378,176); text(870,237,'WEAKER EVIDENCE',19,AMBER,True)
    para('Merged context / values<br/><br/>Probability: not estimated',870,202,330,23,AMBER)

    begin('A retrospective structural check, not calibration')
    para('30 development cells; 20 separate-document replay cells. Both related Rolls-Royce documents stay together.',56,563,1160,25)
    for yy,title,result,detail,color in [
        (345,'Presentation: stronger evidence','10/10 pass','Distinct values and period headers retained.',GREEN),
        (212,'Release: weaker evidence','0/10 pass','All ten numbers are right; period bindings are unresolved.',AMBER)]:
        card(56,yy,1168,113); text(80,yy+76,title,25,NAVY,True)
        text(1000,yy+76,result,25,color,True); text(80,yy+29,detail,21,MUTED)
    para('Selected pages, shared table errors and previously known reports limit this evidence. No blind validation or numeric-error calibration has been completed.',56,171,1160,23,AMBER,max_height=95)

    begin('Why we removed the earlier confidence percentages')
    card(56,324,1168,225)
    para('<b>The earlier calculation:</b> add-one smoothing converted two group counts into percentages. It did not validate their applicability to individual values.',80,513,1110,27)
    para('<b>The correction:</b> show evidence and reviewed counts; leave all per-cell probabilities unassigned.',80,408,1110,27)
    card(56,108,1168,190)
    para('A controlled test changes $98.9 to $89.9 in both parsers: agreement still passes. More output percentages would not fix this blind spot.',80,267,1110,26)
    para('Peterborough: a collapsed one-column table cannot form bound cells and requires review. This example is outside the 50-cell counts.',80,174,1110,21)

    begin('Separate models are built; validation exposes gaps')
    for i,(title,body) in enumerate([
        ('Two models, individual features','Numeric transcription and row/column association are modeled separately.'),
        ('Document-family tests','EDF numeric fold cannot train; Rolls-Royce association predictions struggle.'),
        ('Calibration and inference are implemented','Independent reviews and errors across additional document families are still required.')]):
        yy=407-i*119; card(56,yy,1168,104)
        text(80,yy+65,title,25,GREEN,True); para(body,80,yy+42,1110,22,max_height=60)
    para('Numeric validation scores 40/50 cells but zero of the five errors. The failed fold is preserved. We do not interpret the model outputs as validated correctness probabilities.',56,128,1160,23,AMBER,max_height=65)
    pdf.save()
    print(f'Wrote {page} corrected slides.')


if __name__=='__main__':
    main()
