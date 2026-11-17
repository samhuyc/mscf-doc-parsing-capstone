"""Read-only localhost results panel. No inference or review mutations."""
import argparse
from functools import lru_cache
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from common import ROOT,RUN,RESULTS,read,sha,digest
from copy import deepcopy
from evaluate_table_accuracy import spearman

@lru_cache(maxsize=12)
def cached(path,mtime):return read(Path(path))
def optional(path,default):
 return cached(str(path),path.stat().st_mtime_ns) if path.exists() else default

def data(version='corrected'):
 base=RESULTS/'metric_v2' if version!='original' and (RESULTS/'metric_v2/pairs.json').exists() else RESULTS
 pairs=optional(base/'pairs.json',dict(pairs=[],pending=[],availability=[]))
 development=optional(base/'development_validation.json',dict(summaries=[],predictions=[]))
 fresh=deepcopy(optional(base/'fresh_validation.json',dict(results=[],predictions=[])))
 for item in fresh['results']:
  rs=[r for r in pairs['pairs'] if r['cohort']=='fresh_public' and r['engine']==item['engine'] and r.get(item['target']) is not None and r.get('native_numeric') is not None]
  item['ranking']=dict(spearman=spearman([r['native_numeric'] for r in rs],[r[item['target']] for r in rs]))
 frozen=optional(base/('calibrators_revised.json' if base!=RESULTS else 'calibrators_frozen.json'),{})
 preserved_development=(frozen.get('source_pairs_file_sha256')==development.get('pairs_sha256') and frozen.get('development_pairs_sha256')==digest([r for r in pairs['pairs'] if r['cohort']!='fresh_public']))
 validation_updating=not preserved_development and bool(development.get('pairs_sha256') and development['pairs_sha256']!=sha(base/'pairs.json'))
 if validation_updating:development=dict(summaries=[],predictions=[])
 confirmatory=optional(RESULTS/'round2/test_pairs.json',dict(pairs=[]))
 round2=optional(RESULTS/'round2/test_validation.json',dict(summaries=[],predictions=[]))
 pairs=deepcopy(pairs);pairs.pop('metric_version',None);pairs['pairs']=pairs['pairs']+confirmatory['pairs']
 measurement=optional(RESULTS/'round2/measurement_audit.json',dict(issues={}))
 for row in pairs['pairs']:
  if row['cohort']=='confirmatory' and row['table_id'] in measurement['issues']:row['measurement_issue']=measurement['issues'][row['table_id']]
 return dict(**pairs,development=development,fresh=fresh,round2=round2,measurement_issues=measurement['issues'],metric_version='corrected' if base!=RESULTS else 'original',validation_updating=validation_updating,
             frozen=optional(base/('calibrators_revised.json' if base!=RESULTS else 'calibrators_frozen.json'),{}).get('frozen_utc'),
             progress=optional(ROOT/'prototype/progress.json',{}))

def detail(query):
 version=query.get('version',['corrected'])[0]
 path=RUN/'metric_v2/evaluation_details.json' if version!='original' and (RUN/'metric_v2/evaluation_details.json').exists() else RUN/'evaluation_details.json'
 if query.get('cohort')==['confirmatory']:path=RUN/'confirmatory_evaluation_details.json'
 rows=optional(path,[])
 keys=('cohort','engine','table_id')
 row=next((r for r in rows if all(r[k]==query.get(k,[''])[0] for k in keys)),None)
 if row and row['cohort']=='confirmatory':
  issue=optional(RESULTS/'round2/measurement_audit.json',dict(issues={})).get('issues',{}).get(row['table_id'])
  if issue:row=dict(row,measurement_issue=issue)
 return row

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def respond(self,status,body,kind):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
  self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  url=urlparse(self.path);query=parse_qs(url.query)
  try:
   if url.path in ('/','/index.html'):return self.respond(200,(ROOT/'prototype/panel.html').read_bytes(),'text/html; charset=utf-8')
   if url.path=='/api/data':return self.respond(200,json.dumps(data(query.get('version',['corrected'])[0]),allow_nan=False).encode(),'application/json')
   if url.path in ('/api/detail','/image'):
    row=detail(query)
    if not row:return self.respond(404,b'Unknown evaluated table','text/plain')
    if url.path=='/api/detail':return self.respond(200,json.dumps(row,allow_nan=False).encode(),'application/json')
    path=Path(row['image_path']).resolve()
    if not path.is_relative_to(ROOT.resolve()):return self.respond(403,b'Image outside experiment','text/plain')
    return self.respond(200,path.read_bytes(),'image/png' if path.suffix=='.png' else 'image/jpeg')
   return self.respond(404,b'Not found','text/plain')
  except Exception as exc:return self.respond(500,str(exc).encode(),'text/plain')

def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8768);a=p.parse_args()
 print(f'Native confidence panel: http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
if __name__=='__main__':main()
