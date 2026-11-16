"""Create reference drafts from original PDF text or source-image transcriptions.

No recognizer predictions or confidence values are read. Only selected crop
metadata is used. Digital drafts require visual verification before evaluation.
"""
from pathlib import Path
from regions import NATIVE
from core import read,write,sha,SPONSOR
from numeric_accuracy import numbers
import pymupdf

ROOT=Path(__file__).resolve().parent
SCANNED={
'hippodrome_2025_p020_t01': '''2025 2024
3 116,787,681 114,583,476
(49,553,722) (49,669,638)
67,233,959 64,913,838
(61,723,344) (56,732,754)
6 5,510,615 8,181,084
8 913,167 1,000,725
9 (2,809,776) (3,288,591)
10 169,884 8,941,676
3,783,890 14,834,894
11 (1,056,033) (2,349,942)
2,727,857 12,484,952''',
'hippodrome_2025_p021_t01': '''2025 2024
12 292,280 262,352
13 49,022,342 47,854,347
14 31,001 31,001
49,345,623 48,147,700
16 270,584 294,487
17 39,890,644 26,258,481
24,768,430 30,767,822
64,929,658 57,320,790
18 (32,716,196) (29,889,894)
32,213,462 27,430,896
81,559,085 75,578,596
19 (36,104,541) (33,283,391)
22 3,493,319 3,061,837
(3,493,319) (3,061,837)
41,961,225 39,233,368
24 9,662,983 9,662,983
25 32,298,242 29,570,385
41,961,225 39,233,368''',
'hippodrome_2025_p030_t01': '''2025 2024
660 650
43 38
703 688
2025 2024
24,304,579 22,728,385
2,848,672 2,335,070
683,546 695,312
27,836,797 25,758,767
2025 2024
579,963 522,953
27,200 34,523
607,163 557,476''',
'hippodrome_2025_p036_t01': '''20 2025 2024
35,813,158 33,173,266
35,813,158 33,173,266''',
'peterborough_2025_p002_t01': '''2025 2024
4 967,756 992,467
5 2,278,941 4,936,255
2,751,541 821,700
5,030,482 5,757,955
6 (504,045) (508,936)
4,526,437 5,249,019
5,494,193 6,241,486
7 (1,009,237) (1,046,848)
4,484,956 5,194,638
130 130
40,698 40,698
4,444,128 5,153,810
4,484,956 5,194,638''',
'peterborough_2025_p008_t01': '''At 1 April 2024 1,584,404 236,949 776,063 26,736 2,624,152
Additions 37,138 986 38,124
At 31 March 2025 1,584,404 236,949 813,201 27,722 2,662,276
At 1 April 2024 781,232 199,643 627,408 23,402 1,631,685
Charge 31,688 5,596 24,677 874 62,835
At 31 March 2025 812,920 205,239 652,085 24,276 1,694,520
At 31 March 2025 771,484 31,710 161,116 3,446 967,756
At 31 March 2024 803,172 37,306 148,655 3,334 992,467''',
'peterborough_2025_p009_t01': '''2025 2024
28,862 20,231
2,110,963 4,849,789
28 28
139,088 66,207
2,278,941 4,936,255'''
}


def main():
    destination=ROOT/'accuracy_references.json'
    if destination.exists():raise ValueError('Reference file exists; preserve reviewed edits')
    selection=read(ROOT/'accuracy_selection.json')
    bundle=read(ROOT/'runs/sponsor_all/tables.json')
    entries=[]
    for t in bundle['tables']:
        if t['table_id'] not in selection['table_ids']:continue
        assert sha(ROOT/'runs/sponsor_all'/t['image'])==t['image_sha256']
        scanned=t['table_id'] in SCANNED
        if scanned: text=SCANNED[t['table_id']]
        else:
            path=SPONSOR/'inputs'/(t['document']+'.pdf')
            assert sha(path)==t['source_sha256']
            with pymupdf.open(path) as pdf:
                blocks=pdf[t['page']-1].get_text('dict',clip=pymupdf.Rect(t['bbox_pdf']))['blocks']
                text=' '.join(s['text'] for b in blocks for line in b.get('lines',[]) for s in line['spans'])
        entries.append(dict(table_id=t['table_id'],document=t['document'],page=t['page'],
            image_sha256=t['image_sha256'],source_sha256=t['source_sha256'],
            source_method='assistant_source_image_transcription' if scanned else 'original_pdf_text_layer',
            review_status='assistant_visually_checked' if scanned else 'awaiting_visual_check',
            human_verified=False,reference_text=text,numbers=numbers(text),
            scope='All numeric tokens visible in crop, including years and note numbers; not cell association'))
    write(destination,dict(protocol=selection,references=entries))
    for e in entries:print(e['table_id'],len(e['numbers']),e['numbers'])


if __name__=='__main__':main()
