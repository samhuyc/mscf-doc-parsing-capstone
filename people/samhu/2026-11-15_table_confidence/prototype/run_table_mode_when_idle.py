"""Current-session sequential continuation; does not install a scheduler."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import time
from common import ROOT,RUN,read

def main():
 deadline=datetime.fromisoformat(read(ROOT/'prototype/protocol.json')['deadline_utc'].replace('Z','+00:00'))
 while (RUN/'inference.lock').exists():
  if datetime.now(timezone.utc)>=deadline:raise RuntimeError('Deadline reached before queued experiment')
  time.sleep(10)
 for name in ('sponsor_table_mode','benchmark'):
  subprocess.run([str(ROOT/'work/extra-env/bin/python'),str(ROOT/'prototype/run_batch.py'),'--root',str(RUN/name),'--engines','mineru_table'],cwd=ROOT,check=True)
if __name__=='__main__':main()
