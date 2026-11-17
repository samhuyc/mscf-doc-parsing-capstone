"""Export final scientific plots from saved, issuer-separated measurements."""
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import RESULTS,read

ENGINES=('paddle_vl','glm','monkey','mineru_table')
NAMES=('PaddleOCR-VL','GLM-OCR','MonkeyOCR','MinerU table')

def main():
 out=RESULTS/'round2';dev=read(out/'development_pairs.json')['pairs'];test=read(out/'test_pairs.json')['pairs']
 validation=read(out/'development_validation.json');final=read(out/'test_validation.json');issues=set(read(out/'measurement_audit.json')['issues'])
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'text.color':'#253b4b','axes.labelcolor':'#405565'})
 fig,axes=plt.subplots(2,2,figsize=(11.5,8.5),layout='constrained')
 for ax,engine,name in zip(axes.flat,ENGINES,NAMES):
  for rows,color,label,marker in [(dev,'#829aa8','Development (94 tables)','o'),([r for r in test if r['table_id'] not in issues],'#c67c22','Final test (9 unflagged issuers)','D'),([r for r in test if r['table_id'] in issues],'#5f6468','Scoring issue (2 issuers)','X')]:
   rs=[r for r in rows if r['engine']==engine and r['fact_f1'] is not None and r['native_numeric'] is not None]
   ax.scatter([-math.log10(max(1e-8,1-r['native_numeric'])) for r in rs],[100*r['fact_f1'] for r in rs],c=color,label=label,marker=marker,s=34,alpha=.75,edgecolor='white',linewidth=.4)
  ax.set_title(name,loc='left',weight='bold');ax.set_ylim(-4,104);ax.set_xlim(0,8.2)
  ax.set_xticks([1,2,3,4,6,8],['90%','99%','99.9%','99.99%','99.9999%','≈100%'])
  ax.set_xlabel('Native numeric confidence (expanded near 100%)');ax.set_ylabel('Associated-value F1 (%)');ax.grid(axis='y',color='#e3e9ed');ax.set_axisbelow(True)
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3,frameon=False)
 fig.suptitle('Native certainty does not guarantee correct financial associations',fontsize=15)
 fig.savefig(out/'native_confidence_vs_accuracy.png',dpi=180);fig.savefig(out/'native_confidence_vs_accuracy.svg');plt.close(fig)
 fig,axes=plt.subplots(2,2,figsize=(10,8.5),layout='constrained')
 for ax,engine,name in zip(axes.flat,ENGINES,NAMES):
  ax.plot([0,100],[0,100],ls='--',lw=1,c='#9ba9b2')
  for source,color,label,marker in [(validation,'#829aa8','Issuer-held-out development','o'),({'predictions':[r for r in final['predictions'] if r['table_id'] not in issues]},'#c67c22','Final test · frozen fit','D'),({'predictions':[r for r in final['predictions'] if r['table_id'] in issues]},'#5f6468','Scoring issue (2 issuers)','X')]:
   rs=[r for r in source['predictions'] if r['engine']==engine and r['method']=='header_selected']
   ax.scatter([100*r['prediction'] for r in rs],[100*r['truth'] for r in rs],c=color,label=label,marker=marker,s=34,alpha=.75,edgecolor='white',linewidth=.4)
  ax.set_title(name,loc='left',weight='bold');ax.set_ylim(-4,104);ax.set_xlim(-4,104);ax.set_xlabel('Predicted associated-value F1 (%)');ax.set_ylabel('Measured associated-value F1 (%)');ax.grid(color='#e9edef');ax.set_axisbelow(True)
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3,frameon=False)
 fig.suptitle('Quality forecasts from native probabilities',fontsize=15)
 fig.savefig(out/'heldout_quality_predictions.png',dpi=180);fig.savefig(out/'heldout_quality_predictions.svg');plt.close(fig)
 print('Final figures exported.',flush=True)

if __name__=='__main__':main()
