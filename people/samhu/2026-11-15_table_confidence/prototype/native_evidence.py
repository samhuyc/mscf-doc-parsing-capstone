"""Map unchanged native scores to output text; never use evaluation labels."""
from bisect import bisect_left
from functools import lru_cache
import math
import re
from common import ROOT, NATIVE

NUMBER=re.compile(r'(?<![\w.])(?:(?:[−–-]\s*)?\(?\d+(?:[ ,]\d{3})*(?:\.\d+)?\)?(?:\s*%|\s*(?:bps|ppt))?)(?!\w)',re.I)
MARKUP=re.compile(r'<[^>]*>|(?m:^```[^\n]*$)')


def summary(values):
    values=list(values)
    if any(not math.isfinite(x) or not 0<=x<=1 for x in values):raise ValueError('Invalid native probability')
    if not values:return dict(n=0,mean=None,geometric_mean=None,p10=None,minimum=None)
    ordered=sorted(values)
    return dict(n=len(values),mean=sum(values)/len(values),
                geometric_mean=0.0 if not min(values) else math.exp(sum(math.log(x) for x in values)/len(values)),
                p10=ordered[int(.1*(len(values)-1))],minimum=min(values))

@lru_cache(maxsize=4)
def tokenizer(engine):
    from tokenizers import Tokenizer
    path=NATIVE/'work/mineru-model' if engine in ('mineru','mineru_table') else ROOT/'work/extra-models'/engine
    return Tokenizer.from_file(str(path/'tokenizer.json'))


def stable_spans(ids,decode):
    """Assign byte-fallback pieces to their completed Unicode character.

    Prefix decoding may replace an unfinished Unicode sequence. The suffix
    minimum of agreement with the final decode finds committed boundaries;
    zero-width pieces share the next completed span, preserving every score.
    """
    full=decode(ids); bounds=[0]
    for end in range(1,len(ids)+1):
        prefix=decode(ids[:end]);n=0
        while n<min(len(prefix),len(full)) and prefix[n]==full[n]:n+=1
        bounds.append(n)
    for i in range(len(bounds)-2,-1,-1):bounds[i]=min(bounds[i],bounds[i+1])
    spans=[]
    for i in range(len(ids)):
        start,end=bounds[i],bounds[i+1]
        if end==start:
            j=i+1
            while j<len(ids) and bounds[j+1]==start:j+=1
            end=bounds[j+1] if j<len(ids) else start
        spans.append((start,end))
    return full,spans


def aligned_units(record,engine):
    units=record.get('confidence_units',[]);text=record.get('text','')
    if not units:return dict(status='empty_output',text=text,units=[])
    if engine=='tesseract':
        reconstructed='\n'.join(u['text'] for u in units)
        if reconstructed!=text:raise ValueError('Tesseract text/unit mismatch')
        offset=0;spans=[]
        for u in units:spans.append((offset,offset+len(u['text'])));offset+=len(u['text'])+1
    elif engine=='paddle':
        lines=record['units'];offsets=[];offset=0
        for line in lines:offsets.append(offset);offset+=len(line['text'])+1
        if '\n'.join(x['text'] for x in lines)!=text:raise ValueError('Paddle lines/text mismatch')
        positions={};spans=[]
        for u in units:
            line=u['line_index'];start=positions.get(line,0);piece=u['text']
            if lines[line]['text'][start:start+len(piece)]!=piece:raise ValueError('Paddle character alignment mismatch')
            spans.append((offsets[line]+start,offsets[line]+start+len(piece)));positions[line]=start+len(piece)
        if any(positions.get(i,0)!=len(line['text']) for i,line in enumerate(lines)):raise ValueError('Missing Paddle character coverage')
    else:
        ids=[u['token_id'] for u in units]
        decode=lambda tokens:tokenizer(engine).decode(tokens,skip_special_tokens=False)
        full=decode(ids)
        if all('decoded_span' in u for u in units) and max(u['decoded_span'][1] for u in units)==len(full):
            spans=[tuple(u['decoded_span']) for u in units]
        else:full,spans=stable_spans(ids,decode)
        if full!=text:
            # Streaming detokenizers can trim only leading/trailing whitespace.
            if full.strip()!=text.strip():raise ValueError('Native tokenizer decode differs from emitted text')
            shift=len(full)-len(full.lstrip())-(len(text)-len(text.lstrip()))
            spans=[(max(0,a-shift),min(len(text),max(0,b-shift))) for a,b in spans]
    return dict(status='aligned',text=text,units=[dict(index=i,start=a,end=b,score=u['score'],text=text[a:b]) for i,(u,(a,b)) in enumerate(zip(units,spans))])


def span_units(aligned,spans):
    return [u for u in aligned['units'] if any(u['start']<b and u['end']>a for a,b in spans)]

def numeric_spans(text):
    mask=list(text)
    for m in MARKUP.finditer(text):mask[m.start():m.end()]='\0'*(m.end()-m.start())
    masked=''.join(mask)
    return [(m.start(),m.end()) for m in NUMBER.finditer(masked)]


def visible_spans(text):
    mask=list(text)
    for m in MARKUP.finditer(text):mask[m.start():m.end()]=' '*(m.end()-m.start())
    return [(m.start(),m.end()) for m in re.finditer(r'\S+',''.join(mask))]

def features(record,engine):
    alignment=aligned_units(record,engine);text=alignment['text']
    numeric=numeric_spans(text);structural=[(m.start(),m.end()) for m in MARKUP.finditer(text)]
    content_units=span_units(alignment,visible_spans(text))
    numeric_units=span_units(alignment,numeric);structure_units=span_units(alignment,structural)
    per_number=[dict(text=text[a:b],span=[a,b],confidence=summary(u['score'] for u in span_units(alignment,[(a,b)]))) for a,b in numeric]
    return dict(alignment=alignment['status'],all_tokens=summary(u['score'] for u in record.get('confidence_units',[])),
                numeric_tokens=summary(u['score'] for u in numeric_units),
                visible_tokens=summary(u['score'] for u in content_units),
                numeric_cells=summary(n['confidence']['geometric_mean'] for n in per_number if n['confidence']['n']),
                structure_tokens=summary(u['score'] for u in structure_units),numbers=per_number,
                probability_table_correct=None,calibrated=False,
                note='Native token probabilities describe emitted symbols; omissions have no emitted score.'),alignment
