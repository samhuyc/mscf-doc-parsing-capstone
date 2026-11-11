"""Build a separate slide deck from the existing brief, without modifying it."""
import json
import re
from pathlib import Path

root=Path(__file__).resolve().parent
source=(root/'sponsor_brief.html').read_text()
data=json.loads(re.search(r'<script id="evidence" type="application/json">(.*?)</script>',source,re.S).group(1))
template=(root/'slide_template.html').read_text()
assert template.count('__EVIDENCE_JSON__')==1
payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
(root/'sponsor_slides.html').write_text(template.replace('__EVIDENCE_JSON__',payload))
print('Built sponsor_slides.html; original brief untouched')
