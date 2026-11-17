"""Export scientific figures; never fit a model while plotting."""
from pathlib import Path
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import RESULTS,read

ENGINES=('paddle_vl','glm','monkey','mineru_table')
NAMES={'paddle_vl':'PaddleOCR-VL','glm':'GLM-OCR','monkey':'MonkeyOCR','mineru_table':'MinerU · table task'}
COLORS={'sponsor':'#34738f','benchmark':'#7c8ba1','fresh_public':'#d2842b'}

def cohort(row):return 'fresh_public' if row['cohort']=='fresh_public' else 'benchmark' if row['cohort']=='benchmark' else 'sponsor'
def main():
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#31455a','text.color':'#24384c','axes.titleweight':'bold','figure.facecolor':'white'})
 rows=read(RESULTS/'pairs.json')['pairs']
 fig,axes=plt.subplots(2,2,figsize=(11.8,8.5),layout='constrained')
 for ax,engine in zip(axes.flat,ENGINES):
  valid=[r for r in rows if r['engine']==engine and r['fact_f1'] is not None and r['native_numeric'] is not None]
  for name in COLORS:
   subset=[r for r in valid if cohort(r)==name]
   xs=[-math.log10(max(1e-8,1-r['native_numeric'])) for r in subset]
   ax.scatter(xs,[r['fact_f1']*100 for r in subset],s=30 if name!='fresh_public' else 48,
     c=COLORS[name],label={'sponsor':'Sponsor development','benchmark':'Public benchmark','fresh_public':'Fresh issuers'}[name],
     alpha=.7 if name!='fresh_public' else .95,marker='o' if name!='fresh_public' else 'D',edgecolor='white',linewidth=.5)
  ax.set_title(f"{NAMES[engine]}  ·  n={len(valid)}",loc='left');ax.set_ylim(-4,104);ax.set_xlim(0,8.25)
  ax.set_xticks([1,2,3,4,6,8],['90%','99%','99.9%','99.99%','99.9999%','≈100%'])
  ax.set_xlabel('Native numeric confidence (expanded near 100%)');ax.set_ylabel('Associated financial-value F1 (%)');ax.grid(axis='y',color='#e3e8ed',linewidth=.7);ax.set_axisbelow(True)
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3,frameon=False)
 fig.suptitle('High native certainty does not guarantee correct financial associations',fontsize=15)
 fig.savefig(RESULTS/'native_confidence_vs_accuracy.png',dpi=180);fig.savefig(RESULTS/'native_confidence_vs_accuracy.pdf');plt.close(fig)
 development=read(RESULTS/'development_validation.json');fresh=read(RESULTS/'fresh_validation.json') if (RESULTS/'fresh_validation.json').exists() else {'predictions':[]}
 fig,axes=plt.subplots(2,2,figsize=(10,8.5),layout='constrained')
 for ax,engine in zip(axes.flat,ENGINES):
  dev=[r for r in development['predictions'] if r['engine']==engine and r['cohort']=='development' and r['target']=='fact_f1' and r['method']=='selected_native']
  test=[r for r in fresh['predictions'] if r['engine']==engine and r['training_cohort']=='development' and r['target']=='fact_f1' and r['method']=='selected_native']
  ax.plot([0,100],[0,100],color='#a3adb7',lw=1,ls='--')
  for rs,color,label,marker in [(dev,'#34738f','Issuer-held-out development','o'),(test,'#d2842b','Fresh issuers · frozen fit','D')]:
   ax.scatter([r['prediction']*100 for r in rs],[r['truth']*100 for r in rs],s=30,alpha=.7,c=color,label=label,marker=marker,edgecolor='white',linewidth=.5)
  ax.set_title(NAMES[engine],loc='left');ax.set_xlim(-4,104);ax.set_ylim(-4,104);ax.set_xlabel('Expected association score (%)');ax.set_ylabel('Measured association score (%)');ax.grid(color='#edf0f3',lw=.7);ax.set_axisbelow(True)
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False)
 fig.suptitle('Quality estimates from native probabilities · held-out predictions',fontsize=14)
 fig.savefig(RESULTS/'heldout_quality_predictions.png',dpi=180);fig.savefig(RESULTS/'heldout_quality_predictions.pdf');plt.close(fig)
 print('Exported two figures as PNG and PDF.')
if __name__=='__main__':main()
