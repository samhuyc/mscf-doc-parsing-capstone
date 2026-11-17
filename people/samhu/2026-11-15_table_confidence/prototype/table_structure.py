"""Deterministic table parsing and row/column-associated numeric facts.

Adapters consume only model output. No reference is used to reconstruct a model
result. Unsupported plaintext is explicitly separate from structured output.
"""
from collections import Counter
from decimal import Decimal,InvalidOperation
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
import math
import re
import unicodedata
from copy import deepcopy
from native_evidence import span_units,summary

class Tables(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.sup=0;self.source=text;self.offsets=[0];self.grids=[];self.rows=None;self.row=None;self.cell=None;self.depth=0
        for m in re.finditer('\n',text):self.offsets.append(m.end())
    def position(self):
        line,column=self.getpos();return self.offsets[line-1]+column
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.rows=[]
        if self.depth!=1:return
        if tag=='tr':self.row=[]
        elif tag in ('td','th'):
            attrs=dict(attrs)
            def span(name):
                try:value=int(attrs.get(name,1))
                except ValueError:raise ValueError('Noninteger table span')
                if not 1<=value<=200:raise ValueError('Invalid table span')
                return value
            start=self.position();self.cell=dict(text='',rowspan=span('rowspan'),colspan=span('colspan'),tag=tag,start=start,
                                               content_start=start+len(self.get_starttag_text()))
        elif tag=='sup' and self.cell is not None:self.sup+=1
        elif tag=='br' and self.cell is not None:self.cell['text']+='\n'
    def handle_data(self,data):
        if self.cell is not None and self.depth==1:
            self.cell['text']+=('['+data+']') if self.sup else data
    def handle_endtag(self,tag):
        if tag=='sup':self.sup=max(0,self.sup-1)
        if self.depth==1:
            if tag in ('td','th') and self.cell is not None:
                self.cell.update(content_end=self.position(),end=self.position()+len(tag)+3)
                if self.row is None:self.row=[]
                self.row.append(self.cell);self.cell=None
            elif tag=='tr' and self.row is not None:
                self.rows.append(self.row);self.row=None
            elif tag=='table' and self.rows is not None:
                self.grids.append(expand(self.rows));self.rows=None
        if tag=='table':self.depth=max(0,self.depth-1)

def expand(rows):
    slots={};original=[]
    for r,row in enumerate(rows):
        c=0
        for item in row:
            while (r,c) in slots:c+=1
            item=dict(item,row=r,column=c);original.append(item)
            for dy in range(item['rowspan']):
                for dx in range(item['colspan']):
                    if (r+dy,c+dx) in slots:raise ValueError('Overlapping cells')
                    slots[r+dy,c+dx]=item
            c+=item['colspan']
    if not slots:return dict(cells=[],origins=[],source_cells=[])
    nr=max(r for r,c in slots)+1;nc=max(c for r,c in slots)+1
    if nr*nc>50000:raise ValueError('Unbounded table')
    return dict(cells=[[slots.get((r,c),{}).get('text','').strip() for c in range(nc)] for r in range(nr)],
                origins=[[None if (r,c) not in slots else (slots[r,c]['row'],slots[r,c]['column']) for c in range(nc)] for r in range(nr)],source_cells=original)

def parse_html(text):
    p=Tables(text);p.feed(text)
    if p.depth or p.cell is not None:raise ValueError('Unclosed HTML table')
    return p.grids

OTSL=re.compile(r'<(fcel|ecel|lcel|ucel|xcel|nl)>')
def parse_otsl(text):
    """OTSL cell origins and left/up/both spans; reject invalid references."""
    tokens=list(OTSL.finditer(text));rows=[[]];origins={};source=[];r=c=0
    for i,m in enumerate(tokens):
        kind=m.group(1);end=tokens[i+1].start() if i+1<len(tokens) else len(text)
        if kind=='nl':
            if rows[-1]:rows.append([]);r+=1;c=0
            continue
        if kind in ('fcel','ecel'):
            cell=dict(text=unescape(re.sub(r'<[^>]*>','',text[m.end():end])).strip() if kind=='fcel' else '',
                      row=r,column=c,rowspan=1,colspan=1,start=m.start(),end=end,content_start=m.end(),content_end=end,tag=kind)
            origin=(r,c);origins[origin]=cell;source.append(cell)
        else:
            anchor=(r,c-1) if kind=='lcel' else (r-1,c)
            if anchor not in origins:raise ValueError(f'Invalid {kind} anchor at {r},{c}')
            cell=origins[anchor];origin=(cell['row'],cell['column'])
            if kind=='xcel' and ((r,c-1) not in origins or origins[r,c-1] is not cell):raise ValueError('Inconsistent xcel rectangle')
            cell['rowspan']=max(cell['rowspan'],r-cell['row']+1);cell['colspan']=max(cell['colspan'],c-cell['column']+1)
            origins[r,c]=cell
        rows[-1].append(cell['text']);c+=1
    if rows and not rows[-1]:rows.pop()
    if not rows:return []
    width=max(map(len,rows));rows=[row+['']*(width-len(row)) for row in rows]
    return [dict(cells=rows,origins=[[None if (r,c) not in origins else (origins[r,c]['row'],origins[r,c]['column']) for c in range(width)] for r in range(len(rows))],source_cells=source)]

def parse_output(text,engine):
    if '<table' in text.lower():return dict(status='structured',format='html',grids=parse_html(text))
    if '<fcel>' in text or '<ecel>' in text:return dict(status='structured',format='otsl',grids=parse_otsl(text))
    return dict(status='no_structured_table',format='plain_text',grids=[])

DASH={'-','—','–','−'}
CURRENCY='$£€¥'
def normalize(text):
    text=re.sub(r'</?(?:i|b|strong|em|span|sup|sub|br)(?:\s[^>]*)?\s*/?>','',str(text),flags=re.I)
    text=unicodedata.normalize('NFKC',unescape(text)).replace('\u00ad','').replace(r'\n',' ')
    text=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',text)
    return re.sub(r'\s+',' ',text).strip()
def label(text):
    text=re.sub(r'<sup>(.*?)</sup>',r'[\1]',str(text),flags=re.I|re.S)
    text=re.sub(r'<[^>]+>','',text)
    text=re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+','',text)
    # Explicit annotation markers only; never guess that a bare year digit is a footnote.
    text=re.sub(r'\[\(?(?:\d+(?:\s*,\s*\d+)*|[a-g])\)?\]','',text)
    text=re.sub(r'\([a-g]\)(?=\s|$)','',text)
    text=re.sub(r'(?:\\\(|\$)?\^\{+[\d,\s]+\}+(?:\\\)|\$)?','',text)
    text=normalize(text).lower()
    text=re.sub(r'\b([1-4])q\b',r'q\1',text)
    text=re.sub(r'([£$€¥])',r' \1 ',text)
    text=re.sub(r'(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)',' ',text)
    return re.sub(r'\s+',' ',re.sub(r'[^\w%£$€]+',' ',text)).strip()
def value(text):
    s=normalize(text).replace('−','-').replace('–','-')
    if s.startswith('$') and s.endswith('$') and len(s)>2:s=s[1:-1].strip()
    if s in DASH:return 'DASH'
    s=s.strip();currency=''
    if s and s[0] in CURRENCY:currency=s[0];s=s[1:].strip()
    outer_negative=s.startswith('(') and s.endswith(')')
    if outer_negative:s=s[1:-1].strip()
    suffix=''
    unit=re.search(r'(bps|ppt|pts|bn|million|billion|m)$',s,re.I)
    if unit:
        suffix=unit.group(1).lower();s=s[:unit.start()].strip()
    percent=s.endswith('%')
    if percent:s=s[:-1].strip()
    if s in DASH:return 'DASH'+('%' if percent else suffix)
    inner_negative=s.startswith('(') and s.endswith(')')
    negative=outer_negative or inner_negative
    if inner_negative:s=s[1:-1].strip()
    s=s.replace(',','').replace(' ','')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',s):
        original=normalize(text)
        # Financial guidance ranges and qualifiers are part of correctness.
        allowed=(re.match(r'^(?:at least|at most|up to|approximately|approx\.?|towards|~|[<>≤≥])',original,re.I) or re.fullmatch(r'[\d\s,.$£€¥%()+−–-]+(?:\s*(?:to|bn|m|bps|ppt)\s*[\d\s,.$£€¥%()+−–-]*)?(?:\s*\(at the low-end\))?',original,re.I))
        if allowed and len(original)<=120 and re.search(r'\d',original) and not year_or_date(original):
            canonical=original.lower().replace(',', '').replace('−','-').replace('–','-')
            canonical=re.sub(r'\s*([-~%$£€¥])\s*',r'\1',canonical)
            canonical=re.sub(r'(?<=\d)\.0+(?!\d)','',canonical)
            return 'QUALIFIED:'+canonical
        return None
    try:n=Decimal(s)*(-1 if negative else 1)
    except InvalidOperation:return None
    return ('-' if n<0 else '')+format(abs(n).normalize(),'f')+('%' if percent else suffix)

def year_or_date(text):
    s=normalize(text)
    return bool(re.fullmatch(r'(?:FY\s*)?(?:19|20)\d{2}(?:\s*(?:['+re.escape(CURRENCY)+r']|number|numbers|thousands|millions))*',s,re.I) or
                re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b',s,re.I))

def header_lead(text):
    s=normalize(text).lower()
    return (not s or bool(re.fullmatch(r'[£$€¥]\s*[mb]?|pence|\(?in (?:thousands|millions|billions)\)?',s))
            or bool(re.search(r'\b(?:results|guidance|period|quarter|months|years|year ended|highlights)\b',s)))

def data_start(cells):
    for i,row in enumerate(cells):
        vals=[(c,value(x)) for c,x in enumerate(row[1:],1) if value(x) is not None]
        if not vals:continue
        if all(year_or_date(row[c]) for c,v in vals) and (i==0 or header_lead(row[0])):continue
        # A blank leading label can be a legitimate total or data row.
        if any(v!='DASH' for c,v in vals) or (row[0] and not header_lead(row[0])):return i
    return len(cells)

def _facts(grid,alignment=None):
    cells=grid['cells'];start=data_start(cells)
    if not cells:return dict(facts=[],header_rows=0,status='empty')
    width=max(map(len,cells));headers=[]
    for c in range(width):
        parts=[]
        for row in cells[:start]:
            part=label(row[c] if c<len(row) else '')
            if part and (not parts or part!=parts[-1]):parts.append(part)
        parts.extend(grid.get('global_periods',[]))
        parts.extend('__scale:'+x for x in grid.get('global_scales',[]))
        headers.append(tuple(parts))
    note_cols={c for c,h in enumerate(headers) if any(x in ('note','notes') for x in h)}
    # Some accounts omit the printed 'Note' label. A blank first interior
    # column containing a nondecreasing sequence of small positive integers,
    # before named period columns, is treated as note metadata. No reference.
    if width>=4 and not headers[1] and any(headers[c] for c in range(2,width)):
        items=[normalize(row[1]) for row in cells[start:] if len(row)>1 and normalize(row[1])]
        if len(items)>=3 and all(re.fullmatch(r'[1-9]\d?',x) for x in items):
            nums=list(map(int,items))
            if nums==sorted(nums) and len(set(nums))>=3:note_cols.add(1)
    source={(x['row'],x['column']):x for x in grid.get('source_cells',[])}
    result=[];section=[];previous_label='';unlabeled=0;occurrences=Counter()
    for r,row in enumerate(cells[start:],start):
        numeric=[c for c in range(1,len(row)) if c not in note_cols and value(row[c]) is not None]
        rowname=label(row[0]) if row else ''
        if not numeric:
            if rowname and len(set(label(x) for x in row if label(x)))==1:section=[rowname]
            continue
        if rowname:previous_label=rowname;unlabeled=0
        else:unlabeled+=1;rowname=f'__unlabeled_after:{previous_label}:{unlabeled}'
        occurrences[tuple(section),rowname]+=1
        row_occurrence=occurrences[tuple(section),rowname]
        # Merged values are one emitted cell; keep each semantic column association.
        for c in numeric:
            header=headers[c] or (f'__column_{c}',)
            key=(tuple(section),rowname,header)
            coordinate=grid.get('coordinates',[])
            rr,cc=coordinate[r][c] if coordinate else (r,c)
            item=dict(row=rr,column=cc,row_label=rowname,row_occurrence=row_occurrence,section=list(section),column_header=list(header),value=value(row[c]),raw=row[c],key=key)
            origin=grid.get('origins',[])
            cell=source.get(tuple(origin[r][c])) if origin and origin[r][c] is not None else source.get((r,c))
            if alignment and cell:
                units=span_units(alignment,[(cell['content_start'],cell['content_end'])])
                item['confidence']=summary(u['score'] for u in units)
            result.append(item)
    return dict(facts=result,header_rows=start,status='parsed',column_headers=headers)

def semantic_segments(grid):
    """Normalize representation without consulting the reference.

    Ignore empty margin columns and global spanning captions. Repeated period
    headers start a subtable; explicit row/column associations remain mandatory.
    Source coordinates survive for native-token evidence.
    """
    cells=grid['cells']
    if not cells:return []
    starts=[0]
    first=data_start(cells)
    for i,row in enumerate(cells):
        if i<=first:continue
        # A repeated header has >=2 period columns, no ordinary financial values.
        periods=sum(bool(re.search(r'\b(?:19|20)\d{2}\b',normalize(x))) for x in row[1:])
        numeric=[x for x in row[1:] if value(x) is not None and not year_or_date(x)]
        if periods>=2 and not numeric and header_lead(row[0]):starts.append(i)
    segments=[]
    for a,b in zip(starts,starts[1:]+[len(cells)]):
        rows=deepcopy(cells[a:b]);width=max(map(len,rows),default=0)
        body_start=data_start(rows)
        label_columns=[c for c in range(width) if any(c<len(r) and normalize(r[c]) and value(r[c]) is None for r in rows[body_start:])]
        first_label=min(label_columns) if label_columns else 0
        columns=[c for c in range(width) if any(c<len(r) and normalize(r[c]) for r in rows) and
                 not (c<first_label and all(c>=len(r) or not normalize(r[c]) for r in rows[body_start:]))]
        if not columns:continue
        rows=[[r[c] if c<len(r) else '' for c in columns] for r in rows]
        start=data_start(rows)
        global_scales=set();global_periods=[]
        for row in rows[:start]:
            for c,text in enumerate(row):
                if c==0 or re.match(r'^\(?in (?:thousands|millions|billions)',normalize(text),re.I):
                    global_scales.update(re.findall(r'\bin (thousands|millions|billions)\b',normalize(text).lower()))
                if c>0 and re.match(r'^\(?in (?:thousands|millions|billions)',normalize(text),re.I):row[c]=''
            nonempty=[normalize(x) for x in row if normalize(x)]
            # Global prose captions do not discriminate columns. Pure currency
            # or count-unit rows do: keep them in the period header path.
            if nonempty and len(set(nonempty))==1 and (len(nonempty)==len(row) or (row[0] and not any(row[1:]))):
                pure_unit=bool(re.fullmatch(r'[£$€¥]\s*[mb]?|pence|number|numbers',nonempty[0],re.I))
                if year_or_date(nonempty[0]):global_periods.append(label(nonempty[0]))
                if not pure_unit:
                    for c in range(1,len(row)):row[c]=''
        origins=grid.get('origins',[])
        neworigins=[[origins[r][c] if r<len(origins) and c<len(origins[r]) else None for c in columns] for r in range(a,b)] if origins else []
        segments.append(dict(cells=rows,global_scales=sorted(global_scales),global_periods=global_periods,origins=neworigins,coordinates=[[(r,c) for c in columns] for r in range(a,b)],source_cells=grid.get('source_cells',[])))
    return segments

def facts(grid,alignment=None):
    segments=semantic_segments(grid)
    parsed=[_facts(g,alignment) for g in segments]
    return dict(facts=[f for p in parsed for f in p['facts']],header_rows=parsed[0]['header_rows'] if parsed else 0,
                status='parsed' if parsed else 'empty',segments=len(segments))

def fact_key(fact):
    compact=lambda x:label(x).replace(' ','')
    return (tuple(compact(x) for x in fact['section']),compact(fact['row_label']),fact.get('row_occurrence',1),compact(' '.join(fact['column_header'])),fact['value'])

def fact_score(reference,predicted):
    ref=Counter(fact_key(f) for f in reference);pred=Counter(fact_key(f) for f in predicted)
    matches=sum((ref&pred).values());nr=sum(ref.values());np=sum(pred.values())
    return dict(f1=2*matches/(nr+np) if nr+np else 1.,precision=matches/np if np else float(nr==0),
                recall=matches/nr if nr else float(np==0),matched=matches,reference=nr,predicted=np,exact=ref==pred)

def ordered_grid_score(reference,prediction):
    """Exact normalized cell matching with order-preserving row alignment.

    Columns are fixed; blank padding rows are ignored. Unlike numeric bags,
    swapped values lose credit. Report alongside semantic facts, not as TEDS.
    """
    ref=[r for r in reference if any(normalize(x) for x in r)];pred=[r for r in prediction if any(normalize(x) for x in r)]
    def count(rows):return sum(bool(normalize(c)) for row in rows for c in row)
    def equal(a,b):
        na,nb=value(a),value(b)
        return bool(normalize(a)) and (na==nb if na is not None and nb is not None else label(a)==label(b))
    dp=[[0]*(len(pred)+1) for _ in range(len(ref)+1)]
    for i,a in enumerate(ref,1):
        for j,b in enumerate(pred,1):
            score=sum(equal(x,y) for x,y in zip(a,b))
            dp[i][j]=max(dp[i-1][j],dp[i][j-1],dp[i-1][j-1]+score)
    match=dp[-1][-1];nr,np=count(ref),count(pred)
    return dict(f1=2*match/(nr+np) if nr+np else 1.,matched=match,reference=nr,predicted=np,
                exact=ref==pred,metric='ordered_exact_cell_f1')
