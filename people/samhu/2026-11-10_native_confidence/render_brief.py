"""Build the offline research brief from measured artifacts, with no hand-entered results."""
import base64
import json
import pymupdf

from core import ROOT, SPONSOR, read, sources


def source_crop(document, page, rectangle):
    with pymupdf.open(SPONSOR/'inputs'/(document+'.pdf')) as pdf:
        pixels=pdf[page-1].get_pixmap(matrix=pymupdf.Matrix(2,2),clip=pymupdf.Rect(rectangle))
        return 'data:image/png;base64,'+base64.b64encode(pixels.tobytes('png')).decode()


def render():
    result=ROOT/'results/v2'
    data={
        'documents':sources(),
        'snippets':read(result/'snippet_examples.json'),
        'snippetEvaluation':read(result/'evaluation.json'),
        'pages':read(result/'page_evaluation.json'),
        'pageReferences':read(result/'page_references.json'),
        'decoder':read(result/'decoder_examples.json'),
        'precision':read(result/'precision_audit.json'),
        'runSettings':{e:read(result/e/'settings.json') for e in ('tesseract','paddle','mineru')},
        'images':{
            'dividend':source_crop('cvs_2025q2',6,(645,355,945,440)),
            'repetition':source_crop('rolls_royce_2026h1_release',25,(29,298,571,467)),
        },
    }
    assert data['pages']['reference_pages']==89
    assert data['pages']['excluded_pages']==51
    assert all(data['precision'][e]['pages']>0 for e in ('mineru','paddle'))
    template=(ROOT/'brief_template.html').read_text()
    assert template.count('__EVIDENCE_JSON__')==1
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    (ROOT/'sponsor_brief.html').write_text(template.replace('__EVIDENCE_JSON__',payload))
    print('Built sponsor_brief.html from verified v2 artifacts')


if __name__=='__main__':render()
