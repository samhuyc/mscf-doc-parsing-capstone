"""Score a saved parser prediction with the same project adapters as the handoff."""
import argparse
import ast
import csv
import html
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PAGES=REPO/'people/samhu/2026-09-20_evaluation'
PROTOTYPE=REPO/'people/samhu/2026-11-15_table_confidence/prototype'
TEDS_FILE=REPO/'people/yuyangso/miner_u2.5/minerU2.5.py'
sys.path[:0]=[str(PROTOTYPE),str(PAGES)]
from apted import APTED, Config
from bs4 import BeautifulSoup
from lxml import etree
from lxml import html as lxml_html
from rapidfuzz.distance import Levenshtein
from formats import canonical as to_markup, fact_groups, soup_for
from standard_metric import content_score
import table_structure_v2 as structures

spec=importlib.util.spec_from_file_location('financial_page_scores',PAGES/'score.py')
pages=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)

@lru_cache(maxsize=1)
def get_teds():
    # Import just the scoring definitions. The upstream notebook export also starts a parser.
    names={'edit_distance','TableNode','PubTabNetTEDSConfig','pubtabnet_tokenize','parse_pubtabnet_html','html_to_tree_pubtabnet','count_html_nodes','teds_score'}
    tree=ast.parse(TEDS_FILE.read_text())
    definitions=[t for t in tree.body if isinstance(t,(ast.FunctionDef,ast.ClassDef)) and t.name in names]
    if {t.name for t in definitions}!=names:
        raise ValueError('The upstream TEDS interface has changed')
    scope={'APTED':APTED,'Config':Config,'etree':etree,'html':lxml_html}
    exec(compile(ast.Module(body=definitions,type_ignores=[]),str(TEDS_FILE),'exec'),scope)
    return scope['teds_score']

def table_html(grid):
    cells=defaultdict(list)
    for c in grid['source_cells']:
        attrs=''.join(f' {a}="{c[a]}"' for a in ('rowspan','colspan') if c.get(a,1)>1)
        body=html.escape(' '.join(c['text'].split()),quote=False)
        cells[c['row']].append((c['column'],f'<td{attrs}>{body}</td>'))
    return '<table>'+''.join('<tr>'+''.join(x for _,x in sorted(cells[i]))+'</tr>' for i in range(len(grid['cells'])))+'</table>'

def facts(grids):
    result=[]
    counts=Counter()
    for index,grid in enumerate(grids):
        seen={}
        for fact in structures.facts(grid)['facts']:
            key=(tuple(fact['section']),fact['row_label'])
            row=(fact['row'],key)
            if row not in seen:
                counts[key]+=1
                seen[row]=counts[key]
            result.append({**fact,'grid_index':index,'row_occurrence':seen[row]})
    return result

def table_scores(reference,prediction):
    pred=structures.parse_output(prediction,'prediction')['grids']
    gold=reference['grids']
    truth=facts(gold)
    if not truth:
        raise ValueError('Financial fact F1 requires at least one labeled reference fact.')
    result={'structured':bool(pred),'grits_content':content_score(gold,pred)['f1'] if pred else 0.0,
            'fact_f1':structures.fact_score(truth,facts(pred))['f1'] if pred else 0.0}
    if not reference.get('html'):return result
    gold_html=table_html(structures.parse_output(reference['html'],'gold')['grids'][0])
    predicted=[table_html(g) for g in pred]
    teds=get_teds()
    candidates=[(teds(s,gold_html,False),teds(s,gold_html,True)) for s in predicted]
    full,structure=max(candidates,key=lambda v:v[0]) if candidates else (0.,0.)
    den=max(1,len(candidates))
    result.update(full_teds=full/den,structure_teds=structure/den,
                  numeric_cell_f1=pages.table_scores([gold_html],''.join(predicted))[0]['table_numeric_cell_f1'])
    return result

def upstream_text(value):
    if '<' in value and '>' in value:
        soup=BeautifulSoup(value,'lxml')
        for el in soup(['script','style','noscript','template','iframe']):el.decompose()
        value=soup.get_text(separator=' ',strip=True)
    return re.sub(r'\s+',' ',html.unescape(value)).strip()

def page_scores(annotated,raw_reference,raw_prediction):
    ref={'content':annotated,'format':'html','tables':None,'fact_groups':fact_groups(annotated)}
    scores=pages.score_page(ref,to_markup(raw_prediction,'markdown'))[0]
    control,actual=upstream_text(raw_reference),upstream_text(raw_prediction.strip())
    scores['fin_ed']=Levenshtein.distance(control,actual)/max(len(control),len(actual),1)
    return scores

def row_label(s):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKC',s).lower())

def normal_value(s):
    return s.translate(str.maketrans({'—':'-','–':'-','−':'-'})).replace(',','').replace(' ','')

def filing_scores(sample_id,raw_prediction,reference_file=HERE/'evidence/filing_checks.csv'):
    with reference_file.open(newline='',encoding='utf-8') as f:
        checks=[r for r in csv.DictReader(f) if r['id']==sample_id]
    soup=soup_for(to_markup(raw_prediction,'markdown'),'markdown')
    rows=defaultdict(list)
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            vals=[td.get_text(' ',strip=True) for td in tr.find_all(['td','th'],recursive=False)]
            if vals:rows[row_label(vals[0])].append(vals[1:])
    details=[]
    for check in checks:
        expected=[normal_value(x) for x in json.loads(check['values'])]
        matches=rows[row_label(check['row'])]
        actual=[]
        if len(matches)==1:
            for cell in matches[0]:
                clean=re.sub(r'[$£€\s]','',cell)
                if clean:actual.append(normal_value(clean))
            actual=actual[-len(expected):]
        count=sum(x==y for x,y in zip(actual,expected)) if len(expected)==len(actual) else 0
        details.append({'label':check['row'],'expected':expected,'observed':actual,'matched':count})
    return {'rows':len(details),'rows_exact':sum(r['expected']==r['observed'] for r in details),
            'values':sum(len(r['expected']) for r in details),'value_matches':sum(r['matched'] for r in details),'details':details}

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    sub=cli.add_subparsers(dest='mode',required=True)
    table=sub.add_parser('table');table.add_argument('--reference',type=Path,required=True)
    table.add_argument('--id');table.add_argument('--format',choices=['native','markdown'],default='native')
    page=sub.add_parser('page');page.add_argument('--annotated-html',type=Path,required=True)
    page.add_argument('--matched-html',type=Path,required=True)
    filing=sub.add_parser('filing');filing.add_argument('--id',required=True)
    for p in (table,page,filing):p.add_argument('--prediction',type=Path,required=True)
    args=cli.parse_args();pred=args.prediction.read_text(encoding='utf-8')
    if args.mode=='table':
        ref=json.loads(args.reference.read_text())
        if args.id:ref=ref[args.id]
        result=table_scores(ref,to_markup(pred,'markdown') if args.format=='markdown' else pred)
    elif args.mode=='page':
        result=page_scores(args.annotated_html.read_text(),args.matched_html.read_text(),pred)
    else:result=filing_scores(args.id,pred)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
