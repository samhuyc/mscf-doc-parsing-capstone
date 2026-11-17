"""Wait for the current fresh run, then evaluate the already-frozen fit."""
from datetime import datetime,timezone
import subprocess,time
from common import ROOT,RUN,RESULTS,read,write,sha

def main():
 deadline=datetime.fromisoformat(read(ROOT/'prototype/protocol.json')['deadline_utc'].replace('Z','+00:00'))
 while read(RUN/'fresh_public/prototype_batch.json')['status']=='running':
  if datetime.now(timezone.utc)>=deadline:raise RuntimeError('Goal deadline reached during fresh inference')
  time.sleep(10)
 frozen=read(RESULTS/'calibrators_frozen.json')
 assert all(sha(ROOT/'prototype'/n)==h for n,h in frozen['code_sha256'].items()),'Frozen scoring/calibration code changed'
 snapshot=read(RUN/'fresh_holdout_reference_freeze.json')
 assert sha(RUN/'fresh_public/references.json')==snapshot['references_sha256']
 mark=RUN/'fresh_first_inspection.json'
 if not mark.exists():write(mark,dict(first_inspection_utc=datetime.now(timezone.utc).isoformat(),calibration_frozen_utc=frozen['frozen_utc'],calibration_sha256=sha(RESULTS/'calibrators_frozen.json'),reference_sha256=snapshot['references_sha256']))
 commands=[['extract_evidence.py','--root',str(RUN/'fresh_public')],['evaluate.py'],['analyze.py','--fresh'],['audit.py'],['build_report.py'],['plot_results.py']]
 for args in commands:
  print('Starting',args,flush=True)
  subprocess.run([str(ROOT/'work/extra-env/bin/python'),str(ROOT/'prototype'/args[0]),*args[1:]],cwd=ROOT,check=True)
 print('Fresh frozen evaluation complete.',flush=True)
if __name__=='__main__':main()
