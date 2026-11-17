"""Seal inputs and run all seven configurations, then evaluate once complete."""
from datetime import datetime,timezone
import subprocess
from common import ROOT,RUN,RESULTS,read,write,sha

def main():
 out=RESULTS/'round2';root=RUN/'confirmatory';frozen=read(out/'calibrators_frozen.json')
 refs=read(root/'references.json');tables=read(root/'tables.json')['tables']
 train=sorted(set(x for m in frozen['models'] for x in m['training_issuers']));test=sorted({r['issuer'] for r in refs.values()})
 assert not set(train).intersection(test)
 seal=dict(sealed_utc=datetime.now(timezone.utc).isoformat(),tables_sha256=sha(root/'tables.json'),references_sha256=sha(root/'references.json'),
  calibrators_sha256=sha(out/'calibrators_frozen.json'),evaluator_sha256=sha(ROOT/'prototype/evaluate_confirmatory.py'),development_issuers=train,test_issuers=test,
  requested_crops=40,actual_crops=len(tables),selection_audit_sha256=sha(root/'selection_audit.json'),test_outputs_inspected=False)
 if (out/'test_seal.json').exists():
  old=read(out/'test_seal.json')
  for k in seal:
   if k!='sealed_utc':assert seal[k]==old[k],k
 else:write(out/'test_seal.json',seal)
 python=ROOT/'work/extra-env/bin/python'
 for args in [ ['prototype/run_batch.py','--root',str(root),'--engines','baselines','paddle_vl','glm','monkey','mineru','mineru_table'],
               ['prototype/extract_evidence.py','--root',str(root)],['prototype/evaluate_confirmatory.py'] ]:
  subprocess.run([str(python),*args],cwd=ROOT,check=True)
 print('Confirmatory test complete.',flush=True)

if __name__=='__main__':main()
