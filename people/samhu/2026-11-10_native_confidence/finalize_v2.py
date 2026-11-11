"""Audit complete runs, recompute both reference comparisons, and rebuild the brief."""
from core import ROOT, write
from audit import audit
from evaluate import evaluate
from evaluate_pages import evaluate_pages
from build_evidence import build
from render_brief import render


def main():
    runs=[ROOT/'runs/tesseract', ROOT/'runs/paddle_v2', ROOT/'runs/mineru_v2']
    output=ROOT/'results/v2'
    inventory=[audit(run,output,allow_partial=True) for run in runs]
    # Consolidate all completed page files after targeted runner invocations.
    from core import read
    for run,item in zip(runs,inventory):
        write(run/'documents.json',read(output/item['engine']/'documents.json'))
    write(output/'run_inventory.json',inventory)
    evaluate(runs,output,include_drafts=True)
    evaluate_pages(runs,output)
    build()
    render()


if __name__=='__main__':main()
