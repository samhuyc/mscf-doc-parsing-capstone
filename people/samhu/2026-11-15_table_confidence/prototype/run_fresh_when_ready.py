from datetime import datetime,timezone
from pathlib import Path
import subprocess,time
from common import ROOT,RUN,read

def main():
 deadline=datetime.fromisoformat(read(ROOT/'prototype/protocol.json')['deadline_utc'].replace('Z','+00:00'))
 while True:
  counts=[len(list((RUN/name/'mineru_table').glob('*_*.json'))) for name in ('sponsor_table_mode','benchmark')]
  if counts[0]>=21 and counts[1]>=60 and not (RUN/'inference.lock').exists():break
  if datetime.now(timezone.utc)>=deadline:raise RuntimeError('Deadline reached before fresh evaluation')
  time.sleep(10)
 subprocess.run([str(ROOT/'work/extra-env/bin/python'),str(ROOT/'prototype/run_batch.py'),'--root',str(RUN/'fresh_public'),'--engines','baselines','paddle_vl','glm','monkey','mineru','mineru_table'],cwd=ROOT,check=True)
if __name__=='__main__':main()
