"""Plot measured confidence/correctness pairs without fitting a trend or calibration."""
import argparse
import os
from pathlib import Path
from core import ROOT, read


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--results',type=Path,default=ROOT/'results')
    args=cli.parse_args()
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'work/matplotlib'))
    os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'work/cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report=read(args.results/'evaluation.json')
    engines=list(report['correlations'])
    names={'cvs_2025q2':'CVS','edf_2024':'EDF','hippodrome_2025':'Hippodrome',
           'peterborough_2025':'Peterborough','rolls_royce_2026h1_presentation':'RR slides',
           'rolls_royce_2026h1_release':'RR release'}
    colors=dict(zip(names,['#1776ae','#e08223','#3b9866','#a15fa6','#ca4b4d','#647782']))
    titles={'tesseract':'Tesseract · word scores','paddle':'PaddleOCR · line scores','mineru':'MinerU recognition · token scores'}
    fig,axes=plt.subplots(1,len(engines),figsize=(5*len(engines),4.8),squeeze=False,sharey=True)
    used=[]
    for ax,engine in zip(axes[0],engines):
        rows=[d for d in report['documents'] if d['engine']==engine]
        for d in rows:
            x=d['confidence']['character_weighted_mean']; y=d['selected_span_character_accuracy']
            if x is None or y is None:continue
            name=d['document']
            ax.scatter(x,y,s=65,color=colors[name],label=names[name],edgecolor='white',linewidth=.7,
                       marker='^' if d.get('truncated_pages') else 'o')
            used.append((x,y))
        rho=report['correlations'][engine]['character_weighted_mean']['spearman']
        stat='undefined (constant values)' if rho is None else f'{rho:.3f}'
        pages=sum(d['successful_pages'] for d in rows)
        ax.set_title(f'{titles.get(engine,engine)}\nSpearman: {stat}; {pages}/140 pages',fontsize=11)
        ax.set_xlabel('Native document confidence\n(character-weighted mean)')
        ax.grid(alpha=.2)
        ax.set_axisbelow(True)
    if used:
        xmin=max(0,min(x for x,y in used)-.02)
        ymin=max(0,min(y for x,y in used)-.03)
        for ax in axes[0]:
            ax.set_xlim(xmin,1.005);ax.set_ylim(ymin,1.01)
    axes[0][0].set_ylabel('Character accuracy on selected draft snippets')
    handles,labels=axes[0][0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.015))
    fig.suptitle('Do native confidence summaries track transcription correctness?',fontsize=13,y=.98)
    fig.text(.5,.115,'Six documents • 13 draft spans • different native score scales • triangles: token-limit pages • not whole-document accuracy',ha='center',fontsize=9)
    fig.subplots_adjust(bottom=.29,top=.81,wspace=.12,left=.08,right=.98)
    fig.savefig(args.results/'confidence_vs_accuracy.png',dpi=170)
    fig.savefig(args.results/'confidence_vs_accuracy.svg')
    svg=args.results/'confidence_vs_accuracy.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')


if __name__=='__main__':main()
