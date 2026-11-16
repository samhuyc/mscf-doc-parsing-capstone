"""Standalone scientific figure from recorded confidence/accuracy pairs."""
import argparse
import os
from pathlib import Path
from regions import NATIVE
from core import read
from output_statistics import LABELS

ROOT=Path(__file__).resolve().parent


def plot(root):
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'work/matplotlib'))
    os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'work/cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    root=Path(root); data=read(root/'accuracy/tracking.json')
    colors=dict(cvs_2025q2='#1764a3',edf_2024='#d27313',hippodrome_2025='#267b45',
                peterborough_2025='#9b4797',rolls_royce='#b63e3e')
    labels=dict(cvs_2025q2='CVS',edf_2024='EDF',hippodrome_2025='Hippodrome',peterborough_2025='Peterborough',rolls_royce='Rolls-Royce')
    fig,axes=plt.subplots(2,3,figsize=(14,8),sharey=True)
    quality=[r['numeric']['f1'] for r in data['pairs'] if r['primary_eligible']]
    lower=max(-.02,min(.45,min(quality,default=.5)-.04))
    for ax,(engine,info) in zip(axes.flat,data['models'].items()):
        rows=[r for r in data['pairs'] if r['engine']==engine and r['primary_eligible'] and r['confidence'] is not None]
        s=info['primary'];rho=s.get('spearman')
        note=f'ρ = {rho:.2f}' if rho is not None else ('No numeric-error variation' if rows else 'Queued / no completed selected crops')
        ax.set_title(f'{LABELS[engine]} · n={len(rows)}\n{note}',fontsize=11)
        for issuer in colors:
            points=[r for r in rows if r['issuer']==issuer]
            ax.scatter([r['confidence'] for r in points],[r['numeric']['f1'] for r in points],
                       color=colors[issuer],s=38,alpha=.8,edgecolor='white',linewidth=.4)
        if rows:
            lo=min(r['confidence'] for r in rows)
            ax.set_xlim(max(-.02,lo-max(.005,(1-lo)*.15)),1.003)
        else:ax.set_xlim(0,1)
        ax.set_ylim(lower,1.025);ax.grid(alpha=.18)
        ax.set_xlabel('Native table confidence (axis varies by model)',fontsize=9)
    for ax in axes[:,0]:ax.set_ylabel('Numeric transcription F1')
    fig.suptitle('Does native confidence rank numeric extraction quality?',fontsize=17,y=.99)
    handles=[Line2D([0],[0],marker='o',linestyle='',color=colors[k],label=labels[k]) for k in colors]
    fig.legend(handles=handles,loc='lower center',ncol=5,bbox_to_anchor=(.5,.025),frameon=False)
    fig.text(.5,.002,'19 source-checked crops; assistant-reviewed references; no human verification. Numeric inventory matching does not test cell association.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.08,1,.95))
    for suffix in ('png','svg'):
        fig.savefig(root/'accuracy'/('confidence_vs_numeric_accuracy.'+suffix),dpi=160,bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--root',type=Path,default=ROOT/'runs/sponsor_all')
    plot(cli.parse_args().root)
