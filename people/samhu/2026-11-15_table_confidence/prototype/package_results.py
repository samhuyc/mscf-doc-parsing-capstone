"""Compact provenance and human-readable summary from sealed results."""
from collections import Counter
from datetime import datetime,timezone
import math,statistics
from common import ROOT,OLD,RUN,RESULTS,read,write,sha
from evaluate import reference_sets
from reference_annotations import annotated_reference

NAMES={'paddle':'PP-OCR','tesseract':'Tesseract','paddle_vl':'PaddleOCR-VL','glm':'GLM-OCR','monkey':'MonkeyOCR','mineru':'MinerU text','mineru_table':'MinerU table'}

def main():
 test=read(RESULTS/'round2/test_pairs.json')['pairs'];v=read(RESULTS/'round2/test_validation.json')
 old=read(RESULTS/'metric_v2/pairs.json')['pairs'];allrows=old+test
 manifests=[];references={}
 for cohort,root,refs in list(reference_sets())+[('confirmatory',RUN/'confirmatory',read(RUN/'confirmatory/references.json'))]:
  references[cohort]={tid:annotated_reference(ref) for tid,ref in refs.items()}
  for t in read(root/'tables.json')['tables']:
   if t['table_id'] not in refs:continue
   manifests.append(dict(cohort=cohort,**{k:t[k] for k in ('table_id','document','page','image_sha256','source_sha256','source_dataset','source_row','source_filename','bbox_px','preprocessing') if k in t},issuer=refs[t['table_id']]['issuer']))
 write(RESULTS/'input_manifest.json',dict(tables=manifests,policy='Images and original PDFs remain local; hashes identify exact evaluated pixels. Benchmark document names identify source reports, not fully processed PDFs.'))
 write(RESULTS/'reference_snapshot.json',dict(references=references,human_review_sha256=sha(OLD/'review/financial_ground_truth.json'),policy='Derived annotation snapshots; original human review file remains unchanged.'))
 counts=dict(unique_crops=len({r['image_sha256'] for r in allrows}),outputs=len(allrows),financial_crops=len({r['image_sha256'] for r in allrows if r['financial_reference_eligible']}),
             source_reports=len({m['document'] for m in manifests}),financial_issuers=len({r['issuer'] for r in allrows if r['financial_reference_eligible']}),
             final_test_crops=len({r['image_sha256'] for r in test}),final_test_issuers=len({r['issuer'] for r in test}),
             configurations=len({r['engine'] for r in allrows}),models=6)
 comparison=[]
 for engine,name in NAMES.items():
  rs=[r for r in test if r['engine']==engine]
  s=next((s for s in v['summaries'] if s['engine']==engine and s['method']=='header_selected'),None)
  structured=[r for r in rs if r['fact_f1'] is not None]
  numeric=[r['native_numeric'] for r in rs if r['native_numeric'] is not None]
  comparison.append(dict(engine=engine,name=name,n=len(rs),mean_fact_f1=statistics.mean(r['fact_f1'] for r in structured) if structured else None,
   mean_grits=statistics.mean(r['grits_content_f1'] for r in rs if r['grits_content_f1'] is not None) if structured else None,
   mean_number_recall=statistics.mean(r['financial_value_recall'] for r in rs),numeric_coverage=len(numeric),mean_native_numeric=statistics.mean(numeric) if numeric else None,
   prediction=s,median_recognition_seconds=statistics.median(r['runtime_seconds'] for r in allrows if r['engine']==engine and r['runtime_seconds'] is not None)))
 write(RESULTS/'findings.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),counts=counts,final_comparison=comparison,
  measurement_audit=read(RESULTS/'round2/measurement_audit.json'),final_test_policy=read(RESULTS/'round2/test_seal.json'),original_audit=read(RESULTS/'final_audit.json')['status'],final_test_audit=read(RESULTS/'round2/test_audit.json')['status'],
  important_limits=['Only 11 final test issuers; public benchmark pretraining overlap unknown.','Final sample fell short of 40 because public row retrieval returned 429/502 errors. Selection never used model outputs.',
   'Financial fact F1 is sensitive to deterministic header, label and unit interpretation; GriTS and source inspection remain necessary.',
   'Native token confidence cannot score omissions and does not guarantee a correct table.','First fresh17 became development in round2 after metric repairs; original and sensitivity results remain separate.']))
 lines=['# Results: native confidence prototype','','**Finding: native confidence does not yet reliably predict table accuracy on unseen companies.** No final-test MSE improvement interval excludes zero; the post-inspection nine-table sensitivity also shows no established improvement.','',f"**{counts['outputs']} outputs · {counts['unique_crops']} shared crops · six models.** Final test: {counts['final_test_crops']} tables from {counts['final_test_issuers']} unseen companies, scored with frozen calibration.",'','| Table model | Association F1 | Prediction MAE (pp) ↓ | Mean-only MAE (pp) ↓ | Native feature |','|---|---:|---:|---:|---|']
 for c in comparison:
  if c['prediction']:
   s=c['prediction'];lines.append(f"| {c['name']} | {c['mean_fact_f1']:.1%} | {100*s['mae']:.1f} | {100*s['baseline_mae']:.1f} | {s['feature'].replace('native_','')} |")
 lines+=['','Two final-test tables have documented annotation/header-scoring defects. The table above preserves the original 11-case scores; see [measurement audit and nine-case sensitivity](round2/measurement_audit.json).','','F1 requires the correct value **and** row/column association. Prediction MAE measures error in estimated F1 in percentage points; the baseline always predicts the development mean. These are per-table averages.','',
 'PP-OCR, Tesseract and MinerU text have number-recall controls, not invented table-association scores. MinerU table uses the same checkpoint with its table task.',
 '', '**Limits:** small final test; benchmark pretraining overlap unknown; reference and header-interpretation uncertainty. Confident structural errors remain. Native probability is not whole-table correctness probability.',
 '', '[Open local panel](http://127.0.0.1:8768) · [Full measurements](findings.json) · [Methods](../../prototype/METHODS.md)']
 (RESULTS/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
 print(counts)

if __name__=='__main__':main()
