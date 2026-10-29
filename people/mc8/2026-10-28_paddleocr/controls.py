"""Repeat Sam's image-PDF negative control and native-text sanity check."""
import json
import pymupdf
from common import ROOT, dump
from prepare import sha


def main():
    rows=[]
    for dataset in ['omni','fin']:
        manifest=ROOT/'benchmarks/data'/dataset/'inputs.jsonl'
        if not manifest.is_file():
            continue
        for line in manifest.read_text().splitlines():
            if not line.strip():
                continue
            sample=json.loads(line)
            path=ROOT/'benchmarks'/sample['image_pdf']
            assert sha(path)==sample['image_pdf_sha256']
            with pymupdf.open(path) as pdf:
                chars=sum(len(p.get_text().strip()) for p in pdf)
                assert len(pdf)==1 and chars==0,'Image-PDF unexpectedly contains native text'
            rows.append(dict(id=sample['id'],dataset=dataset,input_sha256=sha(path),native_text_chars=chars,status='expected_empty'))
    apple=ROOT/'early/inputs/apple_2026q3.pdf'
    native=None
    if apple.is_file():
        with pymupdf.open(apple) as pdf:
            chars=len(pdf[0].get_text().strip())
        assert chars>0,'Native-PDF sanity check unexpectedly empty'
        native=dict(document='apple_2026q3',page=1,input_sha256=sha(apple),native_text_chars=chars,status='success',
                    note='Same Apple PDF as original trial. Sam did not commit the exact page used for his native smoke check; this repeat explicitly uses physical page 1.')
    result=dict(parser='pymupdf native text only',image_pdf_controls=rows,native_pdf_control=native,
                note='Input-layer controls only. Native text is never supplied to PaddleOCR predictions.')
    dump(ROOT/'benchmarks/results/native_text_controls.json',result)
    print('Verified native-text-negative image PDFs:',len(rows),'native-PDF-positive:',bool(native),flush=True)


if __name__=='__main__':
    main()
