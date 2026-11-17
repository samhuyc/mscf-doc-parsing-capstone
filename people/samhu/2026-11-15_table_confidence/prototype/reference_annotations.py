"""Source-checked reference repairs, separate from immutable human reviews."""
from copy import deepcopy

CORRECTIONS={
 'edf_2024_p003_t01':{'WACOE/G':'WACO E/G'},
 'rolls_royce_2026h1_presentation_p009_t01':{'Organic Change1':'Organic Change[1]','Organic Change %1':'Organic Change %[1]'},
 'rolls_royce_2026h1_release_p013_t01':{
  'Cost of sales1,2':'Cost of sales[1,2]',
  'Research and development costs2':'Research and development costs[2]',
  'Gain arising on disposal of business3':'Gain arising on disposal of business[3]',
  'Net financing (costs)/income4':'Net financing (costs)/income[4]'}
}

def annotated_reference(ref):
    replacements=CORRECTIONS.get(ref['table_id'],{})
    if not replacements:return ref
    result=deepcopy(ref);edits=[]
    for grid in result['grids']:
        for r,row in enumerate(grid['cells']):
            for c,value in enumerate(row):
                if value in replacements:
                    row[c]=replacements[value];edits.append(dict(row=r,column=c,before=value,after=row[c]))
    if edits:
        result.update(original_reference_kind=ref['reference_kind'],reference_kind='assistant_source_checked',
                      human_verified=False,reference_edits=edits,
                      annotation_reason='Rechecked source crop: restore explicit superscript markers / correct WACO E/G spacing. Original human review remains unchanged.')
    return result
