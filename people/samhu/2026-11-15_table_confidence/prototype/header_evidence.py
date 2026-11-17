"""Native probabilities of model-emitted headers and row labels; no reference."""
from native_evidence import span_units,summary
from table_structure_v2 import parse_output,semantic_segments,data_start,value

FEATURES=('native_header','native_header_p10','native_label','native_label_p10')

def header_features(text,engine,alignment):
 header_spans=[];label_spans=[]
 try:grids=parse_output(text,engine)['grids']
 except ValueError:grids=[]
 for grid in grids:
  roles={}
  for segment in semantic_segments(grid):
   start=data_start(segment['cells'])
   for r,row in enumerate(segment['cells']):
    for c,content in enumerate(row):
     if not content.strip():continue
     position=segment['coordinates'][r][c]
     if r<start:roles[position]='header'
     elif c==0 and value(content) is None:roles[position]='label'
  for cell in grid.get('source_cells',[]):
   role=roles.get((cell['row'],cell['column']))
   if role:
    (header_spans if role=='header' else label_spans).append((cell['content_start'],cell['content_end']))
 headers=summary(u['score'] for u in span_units(alignment,header_spans))
 labels=summary(u['score'] for u in span_units(alignment,label_spans))
 return dict(native_header=headers['geometric_mean'],native_header_p10=headers['p10'],native_label=labels['geometric_mean'],native_label_p10=labels['p10'],header_units=headers['n'],label_units=labels['n'])
