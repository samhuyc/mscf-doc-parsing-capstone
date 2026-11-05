"""Offline, sanitized side-by-side review; no remote assets or model services."""
import json
from pathlib import Path

from chunker import safe_render, slice_spans


def build_review(path, docs, page_chunks, section_chunks, summary, headings):
    data = dict(documents=[dict(document_id=d['document_id'], metadata=d['document_metadata'],
                               pages=[dict(page=p['page'], markdown=p['markdown'], html=safe_render(p['markdown']))
                                      for p in d['pages']]) for d in docs],
                summary=summary, headings=headings, chunks=[])
    lookup = {d['document_id']: d for d in docs}
    for chunk in page_chunks + section_chunks:
        doc = lookup[chunk['document_id']]
        data['chunks'].append(dict(**chunk, html=safe_render(chunk['content']),
                                   context_html=safe_render(slice_spans(doc['pages'], chunk['context_spans']))))
    # A JSON data island must not permit document text to close its script element.
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    Path(path).write_text(TEMPLATE.replace('__DATA__', payload), encoding='utf8')


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'">
<title>Capstone · Chunking Comparison</title><style>
:root{color-scheme:light;--ink:#172b38;--muted:#5c6f7a;--line:#d4dee3;--accent:#006e70;--paper:#fff;--wash:#f3f6f7}
*{box-sizing:border-box}body{margin:0;font:15px/1.65 system-ui,'Segoe UI',sans-serif;color:var(--ink);background:var(--wash)}
header{padding:25px 32px 18px;border-bottom:1px solid var(--line);background:var(--paper)}h1{font-size:24px;margin:0 0 5px}p{margin:8px 0}.sub{color:var(--muted);max-width:1000px}
.flow{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:15px;font-size:13px}.flow strong{color:var(--accent)}
.toolbar{padding:16px 32px;display:flex;gap:14px;align-items:end;flex-wrap:wrap;background:var(--paper)}label{display:block;font-size:12px;color:var(--muted)}select,input,button{font:inherit;border:1px solid var(--line);border-radius:5px;background:var(--paper);padding:7px 10px;color:var(--ink)}input{width:240px}button{cursor:pointer}button.active{background:var(--accent);color:white;border-color:var(--accent)}button:hover{border-color:var(--accent)}
.stats{padding:0 32px 16px;background:var(--paper);display:flex;gap:28px;flex-wrap:wrap;font-size:13px}.stats strong{font-size:19px;margin-right:5px}.note{padding:9px 32px;color:var(--muted);font-size:13px;border-block:1px solid var(--line)}
main{padding:20px 32px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:22px}.panel{min-width:0}h2{font-size:17px;margin:0 0 10px}.paper,.chunk{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:18px;overflow-wrap:anywhere}.paper{position:sticky;top:12px;max-height:78vh;overflow:auto}.chunk{margin-bottom:14px}.chunk h3{font-size:15px;margin:0 0 7px;color:var(--accent)}.meta{font-size:12px;color:var(--muted);margin-bottom:12px}.meta button{padding:2px 7px;font-size:12px;margin:3px}.flags{font-size:12px;color:#795216}.content{overflow:auto;max-height:540px}.content h1,.content h2,.content h3,.content h4,.content h5,.content h6{font-size:15px;color:var(--ink);margin:12px 0 6px}.content table{border-collapse:collapse;font-size:12px;min-width:100%;margin:12px 0}.content td,.content th{border:1px solid var(--line);padding:6px;vertical-align:top;min-width:50px}.content th{background:var(--wash)}.content ul{padding-left:22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,monospace}details{margin-top:12px}summary{cursor:pointer;color:var(--accent);font-size:13px}mark{background:#fff0a8;color:var(--ink)}.empty{padding:24px;color:var(--muted)}footer{padding:12px 32px 30px;color:var(--muted);font-size:12px}.context{border-left:3px solid var(--line);padding-left:12px;margin-top:12px}
@media(max-width:850px){main{grid-template-columns:1fr;padding:16px}.paper{position:static;max-height:440px}header,.toolbar{padding:16px}.stats,.note{padding:10px 16px}input{width:210px}}
</style></head><body>
<header><h1>Capstone · Inspect Chunk Boundaries</h1><div class="sub">Compare saved PyMuPDF4LLM pages on the left with chunks on the right. Click a page reference to highlight the exact source text.</div>
<div class="flow"><span>PDF</span><span>→</span><span>PyMuPDF4LLM + OCR (completed)</span><span>→</span><strong>Chunking (this experiment)</strong><span>→</span><span>Downstream retrieval / RAG</span></div></header>
<div class="toolbar"><div><label for="doc">Document</label><select id="doc"></select></div><div><label for="page">Physical PDF page</label><select id="page"></select></div><div><label>Chunking strategy</label><button id="byPage">Page baseline</button> <button id="bySection" class="active">Sections / paragraphs</button></div><div><label for="query">Keyword filter (not semantic search)</label><input id="query" placeholder="e.g. revenue, EBITDA"></div><div><label><input id="allPages" type="checkbox" style="width:auto">Show chunks from all pages</label></div></div>
<div class="stats" id="stats"></div><div class="note">Exact coverage is checked against saved parser text, not against the original PDF. Heading hierarchy and adjacent table context are heuristic; source content is preserved.</div>
<main><section class="panel"><h2 id="sourceTitle">Original parsed page</h2><div class="paper" id="source"></div></section><section class="panel"><h2 id="chunksTitle">Chunks</h2><div id="chunks"></div></section></main>
<footer>Size is measured in raw Markdown characters, with a default soft limit of 4,000 characters—not a model token limit. Complete tables and other atomic blocks may exceed it. Cross-page tables are not automatically merged; image content is not reprocessed.</footer>
<script type="application/json" id="data">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
let strategy='section';
const flagNames={soft_budget_exceeded:'Exceeds soft size budget',oversized_atomic_block:'Atomic block exceeds size budget',table_preserved_as_exported:'Exported table structure preserved',no_visible_text:'No searchable visible text'};
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
for(const d of data.documents){const o=node('option',d.document_id);o.value=d.document_id;$('doc').append(o)}
function current(){return data.documents.find(d=>d.document_id===$('doc').value)}
function unicodeSlice(text,start,end){return Array.from(text).slice(start,end).join('')}
function source(location){const p=current().pages[Number($('page').value)-1];$('sourceTitle').textContent='Original parsed page · PDF page '+p.page;$('source').replaceChildren();
 if(location){const hint=node('p','Highlighted range: source Markdown characters ['+location.start+', '+location.end+')','meta');const pre=node('pre');pre.append(document.createTextNode(unicodeSlice(p.markdown,0,location.start)),node('mark',unicodeSlice(p.markdown,location.start,location.end)),document.createTextNode(unicodeSlice(p.markdown,location.end)));$('source').append(hint,pre)}
 else{const rendered=node('div',undefined,'content');rendered.innerHTML=p.html;$('source').append(rendered)}}
function locate(s){$('page').value=String(s.page);source(s);$('source').scrollTop=0;const mark=$('source').querySelector('mark');if(mark)mark.scrollIntoView({block:'nearest'})}
function render(){source();const doc=current(),r=data.summary.documents.find(d=>d.document_id===doc.document_id);$('stats').replaceChildren();for(const [value,label] of [[r.pages,'source pages'],[r.page.chunk_count,'page chunks'],[r.section.chunk_count,'section chunks'],[r.section.table_blocks_preserved,'intact table blocks']]){const s=node('span');s.append(node('strong',value),document.createTextNode(label));$('stats').append(s)}$('stats').append(node('span','Coverage: exact character match'));
 $('byPage').classList.toggle('active',strategy==='page');$('bySection').classList.toggle('active',strategy==='section');
 const q=$('query').value.toLocaleLowerCase().trim(),selected=Number($('page').value);
 const chunks=data.chunks.filter(c=>c.document_id===doc.document_id&&c.strategy===strategy&&($('allPages').checked||c.source_spans.some(s=>s.page===selected))&&(!q||c.retrieval_text.toLocaleLowerCase().includes(q)));
 $('chunksTitle').textContent=(strategy==='page'?'Page baseline':'Sections / paragraphs')+' · '+chunks.length+' chunks shown';$('chunks').replaceChildren();
 for(const [i,c] of chunks.entries()){const card=node('article',undefined,'chunk');card.append(node('h3',c.section_path.join(' › ')||'Unlabeled section / page content'));
 const meta=node('div',c.char_count.toLocaleString()+' characters · '+c.chunk_id,'meta');meta.append(node('br'));for(const s of c.source_spans){const b=node('button','PDF p'+s.page+' ['+s.start+','+s.end+')');b.addEventListener('click',()=>locate(s));meta.append(b)}card.append(meta);
 if(c.flags.length)card.append(node('p',c.flags.map(x=>flagNames[x]||x).join(' · '),'flags'));
 const content=node('div',undefined,'content');content.innerHTML=c.html;card.append(content);
 if(c.context_spans.length){const ctx=node('details',undefined,'context');ctx.append(node('summary','Adjacent retrieval context (footnote association is unverified)'));const body=node('div',undefined,'content');body.innerHTML=c.context_html;ctx.append(body);card.append(ctx)}
 const raw=node('details');raw.append(node('summary','View original Markdown and source fields'),node('pre',c.content),node('pre',JSON.stringify({source_spans:c.source_spans,heading_evidence:c.heading_evidence,context_spans:c.context_spans,document_metadata:c.document_metadata},null,2)));card.append(raw);$('chunks').append(card)}
 if(!chunks.length)$('chunks').append(node('div','No chunks match this page and keyword. Try selecting "Show chunks from all pages".','empty'))}
function changeDoc(){$('page').replaceChildren();for(const p of current().pages){const o=node('option',p.page);o.value=p.page;$('page').append(o)}$('page').value=String(Math.min(current().document_id==='edf_2024'?4:2,current().pages.length));render()}
$('doc').addEventListener('change',changeDoc);$('page').addEventListener('change',render);$('allPages').addEventListener('change',render);$('query').addEventListener('input',render);$('byPage').addEventListener('click',()=>{strategy='page';render()});$('bySection').addEventListener('click',()=>{strategy='section';render()});changeDoc();
</script></body></html>'''
