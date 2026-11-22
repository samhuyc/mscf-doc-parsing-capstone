"""Build a concise presentation from saved scores and exploratory issuer CV."""
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/capstone-summary-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent
CPU = OUT.parents[2]
ROOT = CPU.parents[2]
SAM = ROOT/'people/samhu/2026-11-15_table_confidence/results/native_prototype'
RUN = OUT.parent
FILES = [RUN/'batch-results/batch-03.json', RUN/'batch-results/batch-03-metrics.json', SAM/'findings.json']
summary, details, sam = [json.loads(p.read_text()) for p in FILES]
FORECAST_FILE = OUT/'exploratory_development_forecasts.json'
forecasts = json.loads(FORECAST_FILE.read_text())
FILES.append(FORECAST_FILE)
assert summary['completed_tables'] == details['counts']['unique_crops'] == 300
assert summary['scored_outputs'] == 2100
engines = details['engines']
saved = {r['engine']: r for r in sam['final_comparison']}
MODELS = ['paddle_vl', 'mineru_table', 'glm', 'monkey']
NAMES = {'paddle_vl': 'PaddleOCR-VL', 'mineru_table': 'MinerU table',
         'glm': 'GLM-OCR', 'monkey': 'MonkeyOCR',
         'tesseract': 'Tesseract', 'paddle': 'PP-OCRv5', 'mineru': 'MinerU text'}
NAVY, TEAL, BLUE, GOLD = '#142A43', '#007E80', '#657CB6', '#B67C14'
INK, MUTED, LIGHT, GRID = '#263B50', '#5A6C7E', '#F0F5F8', '#E1E8EE'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12,
    'text.color': INK, 'axes.labelcolor': MUTED, 'xtick.color': MUTED,
    'ytick.color': INK, 'pdf.fonttype': 42, 'ps.fonttype': 42})


def text(fig, x, y, value, size=13, color=INK, weight='normal', **kwargs):
    return fig.text(x, y, value, fontsize=size, color=color, fontweight=weight,
                    va='top', **kwargs)


def panel(fig, x, y, w, h, color=LIGHT):
    fig.patches.append(FancyBboxPatch((x, y), w, h,
        boxstyle='round,pad=0.008,rounding_size=0.012', transform=fig.transFigure,
        facecolor=color, edgecolor='none', zorder=-10))


def page(title, subtitle, number):
    fig = plt.figure(figsize=(16, 9), facecolor='white')
    fig.patches.append(plt.Rectangle((0, .985), 1, .015, transform=fig.transFigure,
                                     color=TEAL, linewidth=0))
    text(fig, .045, .95, 'MSCF CAPSTONE  /  NOVEMBER 18, 2026', 11, TEAL, 'bold')
    text(fig, .045, .903, title, 28, NAVY, 'bold')
    text(fig, .045, .843, subtitle, 12, MUTED)
    text(fig, .045, .035, '300 tables completed  •  Development analysis  •  November 18, 2026', 9, MUTED)
    text(fig, .955, .035, f'{number} / 3', 10, MUTED, ha='right')
    return fig


def style(ax, xlim=(0, 100), ticks=(0, 25, 50, 75, 100)):
    ax.set_xlim(*xlim)
    ax.set_xticks(ticks)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color=GRID, linewidth=.8)
    ax.tick_params(axis='both', length=0, pad=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor('none')


def save(pdf, fig, stem):
    pdf.savefig(fig)
    fig.savefig(OUT/f'{stem}.png', dpi=110, facecolor='white')
    plt.close(fig)


def cohort_legend(fig, top, sam_label='Sam · held-out test', our_label='Our run · development'):
    handles = [Line2D([], [], marker='s', color='none', markerfacecolor=BLUE,
                       markeredgecolor=BLUE, markersize=7, label=sam_label),
               Line2D([], [], marker='o', color='none', markerfacecolor=TEAL,
                       markeredgecolor=TEAL, markersize=7, label=our_label)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, top),
               ncol=2, frameon=False, fontsize=11, columnspacing=2.5, handletextpad=.5)


def paired_scores(ax, order, metric, decimals=1, font=10):
    for i, engine in enumerate(order):
        s, o = 100*saved[engine][metric], 100*engines[engine][metric]
        ax.plot([s, o], [i+.19, i-.19], color=GRID, linewidth=2, zorder=1)
        ax.scatter(s, i+.19, s=65, marker='s', color=BLUE, zorder=3)
        ax.scatter(o, i-.19, s=65, marker='o', color=TEAL, zorder=3)
        for value, yy, color in ((s, i+.19, BLUE), (o, i-.19, TEAL)):
            shift, ha = (1.6, 'left') if value < 12 else (-1.6, 'right')
            ax.text(value+shift, yy, f'{value:.{decimals}f}',
                    va='center', ha=ha, fontsize=font, color=color)
    ax.set_yticks(np.arange(len(order)), [NAMES[e] for e in order])
    ax.set_ylim(len(order)-.5, -.5)


def paired_confidence(ax, metric):
    for i, e in enumerate(MODELS):
        row = forecasts['engines'][e]['correlations']
        s, o = row['sam_test_'+metric], row['ours_'+metric]
        ax.plot([s, o], [i+.19, i-.19], color=GRID, linewidth=2, zorder=1)
        for value, yy, color, marker in ((s, i+.19, BLUE, 's'), (o, i-.19, TEAL, 'o')):
            ax.scatter(value, yy, s=55, color=color, marker=marker, zorder=3)
            ax.text(value-.025, yy, f'{value:.3f}', ha='right', va='center', fontsize=9.5, color=color)
    ax.set_yticks(np.arange(4), [NAMES[e] for e in MODELS])
    ax.set_ylim(3.5, -.5)
    ax.tick_params(axis='y', labelsize=10)


def forecast_plot(ax, metric, multiplier):
    maximum = 0
    for i, e in enumerate(MODELS):
        row = forecasts['engines'][e]
        for key, yy, color, marker in (('sam_development_cv', i+.20, BLUE, 's'),
                                       ('ours_development_cv', i-.20, TEAL, 'o')):
            score = row[key]
            value, baseline = multiplier*score[metric], multiplier*score['baseline_'+metric]
            maximum = max(maximum, value, baseline)
            ax.plot([value, baseline], [yy, yy], color=color, alpha=.35, linewidth=2)
            ax.scatter(baseline, yy, s=75, facecolor='white', edgecolor=color, linewidth=1.5, marker=marker, zorder=2)
            ax.scatter(value, yy, s=60, color=color, marker=marker, zorder=3)
            ax.annotate(f'{value:.2f}' if metric == 'mae' else f'{value:.4f}',
                        (value, yy), xytext=(-9, 0), textcoords='offset points',
                        ha='right', va='center', fontsize=9.5, color=color)
    ax.set_yticks(np.arange(4), [NAMES[e] for e in MODELS])
    ax.set_ylim(3.5, -.5)
    stop = np.ceil(maximum*1.1/(10 if metric == 'mae' else .05))*(10 if metric == 'mae' else .05)
    style(ax, (0, stop), np.linspace(0, stop, 6))


target = OUT/'confidence_results_summary_2026-11-18.pdf'
with PdfPages(target, metadata={'Title': 'Financial table extraction — results after 300 tables',
    'Author': 'MSCF Capstone', 'Subject': 'Results and comparison with Sam; presentation November 18, 2026',
    'Keywords': 'OCR, financial tables, F1, GriTS, confidence, development'}) as pdf:
    fig = page('Financial table extraction: results after 300 tables',
               'Same six models and seven configurations as Sam, using his financial-association scoring functions on our CPU run.', 1)
    cards = [('Our run: 300 tables', '2,100 successful outputs · 9 issuers · 55 source reports'),
             ('Sam: 109 tables', '763 outputs overall · final test: 11 tables from 11 issuers')]
    for x, (value, label) in zip((.045, .515), cards):
        panel(fig, x, .715, .44, .09)
        text(fig, x+.015, .786, value, 22, NAVY, 'bold')
        text(fig, x+.015, .746, label, 11, MUTED)
    cohort_legend(fig, .706)

    text(fig, .045, .655, 'Financial fact F1', 17, NAVY, 'bold')
    text(fig, .045, .619, 'Correct value plus row/column association; structured modes only.', 10.5, MUTED)
    ax = fig.add_axes([.175, .31, .315, .275])
    paired_scores(ax, MODELS, 'mean_fact_f1', decimals=2)
    style(ax, (30, 102), (40, 60, 80, 100))
    ax.set_xlabel('Financial fact F1 (%)', fontsize=11, labelpad=9)

    text(fig, .565, .655, 'Number recall: all seven configurations', 17, NAVY, 'bold')
    text(fig, .565, .619, 'Text-only modes are evaluated on number recall, without invented F1.', 10.5, MUTED)
    ax2 = fig.add_axes([.715, .31, .235, .275])
    order = MODELS + ['mineru', 'paddle', 'tesseract']
    paired_scores(ax2, order, 'mean_number_recall', font=9)
    ax2.tick_params(axis='y', labelsize=10)
    style(ax2, (0, 104), (0, 25, 50, 75, 100))
    ax2.set_xlabel('Reference numbers recovered (%)', fontsize=10.5, labelpad=9)

    panel(fig, .045, .13, .91, .105)
    text(fig, .06, .216, 'Shared finding: recovering numbers is easier than preserving financial associations', 12, TEAL, 'bold')
    text(fig, .06, .184, 'GLM-OCR in Sam’s run: 97.69% number recall versus 72.15% financial F1.', 13, NAVY)
    text(fig, .06, .153, 'GLM-OCR in our run: 91.60% number recall versus 63.16% financial F1. The same gap remains visible.', 13, NAVY)
    text(fig, .045, .105, 'Plot scope: Sam’s 11-table final test versus our development sample. Our F1 / number recall use 283 tables; 17 have no eligible facts.', 10, MUTED)
    text(fig, .045, .078, 'Sam’s 109-table total includes development and test. Different input cohorts and runtimes mean these averages are descriptive comparisons.', 10, MUTED)
    save(pdf, fig, 'page-1-preview')

    fig = page('Confidence and content: correlations and error AUC',
               'Sam: 11 test tables. Our run: 282–283 development rows for confidence; 300 for GriTS. Every plot compares both runs.', 2)
    cohort_legend(fig, .811)
    text(fig, .045, .757, 'Spearman rank correlation · 95% issuer intervals', 16, NAVY, 'bold')
    text(fig, .565, .757, 'Pearson linear correlation', 16, NAVY, 'bold')
    ax = fig.add_axes([.175, .475, .32, .22])
    for i, e in enumerate(MODELS):
        for ranking, yy, color, marker in (
            (saved[e]['prediction']['ranking'], i+.19, BLUE, 's'),
            (engines[e]['ranking_by_split']['development'], i-.19, TEAL, 'o')):
            lo, hi = ranking['spearman_issuer_bootstrap_95']
            rho = ranking['spearman']
            ax.errorbar(rho, yy, xerr=[[rho-lo], [hi-rho]], fmt=marker, color=color,
                         ecolor=color, capsize=3, markersize=6.5, linewidth=1.7)
            ax.text(1.05, yy, f'{rho:.3f}', ha='right', va='center', fontsize=9.5, color=color)
    ax.axvline(0, color=MUTED, linestyle=':', linewidth=1)
    ax.set_yticks(np.arange(4), [NAMES[e] for e in MODELS])
    ax.set_ylim(3.5, -.5)
    ax.tick_params(axis='y', labelsize=10)
    style(ax, (-.65, 1.08), (-.5, 0, .5, 1))
    ax.set_xlabel('Native numeric confidence versus financial F1', fontsize=10, labelpad=8)

    ax2 = fig.add_axes([.695, .475, .255, .22])
    paired_confidence(ax2, 'pearson')
    style(ax2, (-.2, .9), (0, .2, .4, .6, .8))
    ax2.axvline(0, color=MUTED, linestyle=':', linewidth=1)
    ax2.set_xlabel('Pearson coefficient (derived from saved pairs)', fontsize=10, labelpad=8)

    text(fig, .045, .404, 'GriTS: similarity of cell contents', 16, NAVY, 'bold')
    text(fig, .565, .404, 'Error-detection AUC · higher is better', 16, NAVY, 'bold')
    ax3 = fig.add_axes([.175, .15, .32, .21])
    paired_scores(ax3, MODELS, 'mean_grits', decimals=2, font=9.5)
    ax3.tick_params(axis='y', labelsize=10)
    style(ax3, (75, 102), (75, 80, 85, 90, 95, 100))
    ax3.set_xlabel('GriTS content F1 (%)', fontsize=10, labelpad=8)
    ax4 = fig.add_axes([.695, .15, .255, .21])
    paired_confidence(ax4, 'error_auc')
    style(ax4, (0, 1.03), (0, .25, .5, .75, 1))
    ax4.axvline(.5, color=MUTED, linestyle=':', linewidth=1)
    ax4.set_xlabel('AUC · low confidence signals F1 < 0.95', fontsize=10, labelpad=8)
    text(fig, .045, .078, 'Spearman measures ranking; Pearson measures linear association. AUC: 0.5 = chance, 1 = perfect error ranking. Missing confidence is excluded.', 9.5, MUTED)
    text(fig, .045, .055, 'Shared pattern: PaddleOCR-VL / MinerU table lead extraction; MinerU table has the strongest Spearman in both. The leading F1 pair swaps order.', 9.5, MUTED)
    save(pdf, fig, 'page-2-preview')

    fig = page('Forecasting financial F1: MAE and MSE',
               'Exploratory development validation: hold out each issuer; select native features and fit isotonic regression using other issuers only.', 3)
    for x, value, label in (
        (.045, 'Our CV: 283 tables · 9 issuers', 'Each eligible table is forecast once while its entire issuer is held out.'),
        (.515, 'Sam CV: 94 tables · 42 issuers', 'Saved nested development validation; same 12-feature selection method.')):
        panel(fig, x, .715, .44, .09)
        text(fig, x+.015, .786, value, 20, NAVY, 'bold')
        text(fig, x+.015, .746, label, 10, MUTED)
    cohort_legend(fig, .706, 'Sam · development CV', 'Our run · development CV')
    text(fig, .045, .655, 'Mean absolute error · lower is better', 17, NAVY, 'bold')
    text(fig, .565, .655, 'Mean squared error · lower is better', 17, NAVY, 'bold')
    ax = fig.add_axes([.175, .35, .32, .24])
    forecast_plot(ax, 'mae', 100)
    ax.set_xlabel('MAE (percentage points of F1)', fontsize=10.5, labelpad=8)
    ax2 = fig.add_axes([.695, .35, .255, .24])
    forecast_plot(ax2, 'mse', 1)
    ax2.set_xlabel('MSE (F1 on the 0–1 scale)', fontsize=10.5, labelpad=8)
    text(fig, .045, .283, 'Filled markers = fitted native-feature forecast. Open markers = mean-F1 baseline learned from the outer training issuers.', 10.5, MUTED)
    text(fig, .045, .246, 'Sam’s separate final test · 11 tables (not the CV points above)', 12, NAVY, 'bold')
    tab_ax = fig.add_axes([.045, .102, .535, .126])
    tab_ax.axis('off')
    cells = []
    for e in MODELS:
        p = forecasts['engines'][e]['sam_final_test']
        cells.append([NAMES[e], f"{100*p['mae']:.2f}", f"{100*p['baseline_mae']:.2f}",
                      f"{p['mse']:.4f}", f"{p['baseline_mse']:.4f}"])
    tab = tab_ax.table(cellText=cells, colLabels=['Model', 'MAE (pp)', 'Base MAE (pp)', 'MSE', 'Base MSE'],
        colWidths=[.28, .16, .20, .16, .20], cellLoc='center', bbox=[0, 0, 1, 1])
    tab.auto_set_font_size(False)
    tab.set_fontsize(9.5)
    for (row, col), cell in tab.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_facecolor(LIGHT if row == 0 or row % 2 == 0 else 'white')
        cell.get_text().set_color(NAVY if row == 0 else INK)
        if row == 0:
            cell.get_text().set_weight('bold')
    text(fig, .615, .246, 'Interpretation and limits', 12, TEAL, 'bold')
    text(fig, .615, .214, 'GLM and Monkey reduce MSE versus baseline', 11, NAVY)
    text(fig, .615, .187, 'in both development validations. Our four CV', 11, NAVY)
    text(fig, .615, .160, 'point estimates improve MSE; final held-out', 11, NAVY)
    text(fig, .615, .133, 'forecast performance is still unavailable.', 11, NAVY)
    text(fig, .045, .078, 'Public references need audit: our sample retains one flagged case; Sam’s final test retains two. Issuer counts and datasets differ.', 9.5, MUTED)
    text(fig, .045, .055, 'Exploratory CV leaves the production calibration unchanged. No OCR was rerun. Forecast error is distinct from whole-table correctness probability.', 9.5, MUTED)
    save(pdf, fig, 'page-3-preview')

provenance = dict(pdf=target.name, completed_tables=300, financial_tables=283,
    completed_outputs=2100, pages=3, forecast_results='Exploratory nested leave-one-issuer-out development CV; final held-out forecasts unavailable',
    sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES})
(OUT/'summary-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
print(target)
