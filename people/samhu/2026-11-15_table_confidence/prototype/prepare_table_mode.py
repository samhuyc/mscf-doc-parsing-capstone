"""Reuse the exact 21 development images for the official MinerU table task."""
from copy import deepcopy
from common import RUN,read,write
from evaluate import reference_sets

def main():
 tables=[];refs={}
 for cohort,root,references in reference_sets():
  if cohort not in ('sponsor_development','repairs'):continue
  for t in read(root/'tables.json')['tables']:
   tid=t['table_id']
   if tid not in references:continue
   copy=deepcopy(t);copy['image']=str((root/t['image']).resolve());copy['models']={};tables.append(copy)
   refs[tid]=references[tid]
 root=RUN/'sponsor_table_mode'
 write(root/'references.json',refs)
 write(root/'tables.json',dict(settings=dict(purpose='Official MinerU table task; identical shared pixels',render_dpi=200,
      prompt_source='https://github.com/opendatalab/mineru-vl-utils/blob/main/mineru_vl_utils/mineru_client.py',
      native_logits='Unmodified; greedy decoding; publisher sampling penalties remain disabled as in original experiment'),pages=[],tables=tables))
 print('Prepared',len(tables),'identical images for the table-mode comparison.')
if __name__=='__main__':main()
