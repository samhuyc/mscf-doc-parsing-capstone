# Table comparison: UK filing, physical PDF page 8

Excerpts from the original four-page sample runs (8 September 2026),
with table contents unchanged. The sample contained physical pages 4, 8, 9 and 16.
Source: Lamray Holdings Limited, 2012 annual report; see the source link in the README.

The OCR/layout output merges the two interest rows and renders the 2011 tax
amount as `(4.295)`. The VLM separates the interest rows and preserves `(4,295)`.

## OCR/layout (`pipeline`)

<table><tr><td></td><td>Notes</td><td>2012 £</td><td>2011 £</td></tr><tr><td>Turnover</td><td>2</td><td>3,181,093</td><td>4,205,103</td></tr><tr><td>Cost of sales</td><td></td><td>(2,053,743)</td><td>(2,866,555)</td></tr><tr><td>Gross profit</td><td></td><td>1,127,350</td><td>1,338,548</td></tr><tr><td>Distribution costs</td><td></td><td>(357,776)</td><td>(351,346)</td></tr><tr><td>Administrative expenses</td><td></td><td>(865,879)</td><td>(968,713)</td></tr><tr><td>Operating (loss)/profit</td><td>3</td><td>(96,305)</td><td>18,489</td></tr><tr><td>Other interest receivable and similar</td><td></td><td></td><td></td></tr><tr><td>income Interest payable and similar charges</td><td>4</td><td>11 (12,712)</td><td>133 (6,157)</td></tr><tr><td>(Loss)/profit on ordinary activities</td><td></td><td></td><td></td></tr><tr><td>before taxation</td><td>3</td><td>(109,006)</td><td>12,465</td></tr><tr><td>Tax on (loss)/profit on ordinary activities</td><td>5</td><td>5,450</td><td>(4.295)</td></tr><tr><td></td><td></td><td></td><td></td></tr><tr><td>(Loss)/profit on ordinary activities after taxation</td><td></td><td>(103,556)</td><td>8,170</td></tr></table>

## Local vision-language model (`vlm-engine`)

<table><tr><td></td><td>Notes</td><td>2012£</td><td>2011£</td></tr><tr><td>Turnover</td><td>2</td><td>3,181,093</td><td>4,205,103</td></tr><tr><td>Cost of sales</td><td></td><td>(2,053,743)</td><td>(2,866,555)</td></tr><tr><td>Gross profit</td><td></td><td>1,127,350</td><td>1,338,548</td></tr><tr><td>Distribution costs</td><td></td><td>(357,776)</td><td>(351,346)</td></tr><tr><td>Administrative expenses</td><td></td><td>(865,879)</td><td>(968,713)</td></tr><tr><td>Operating (loss)/profit</td><td>3</td><td>(96,305)</td><td>18,489</td></tr><tr><td>Other interest receivable and similar income</td><td></td><td>11</td><td>133</td></tr><tr><td>Interest payable and similar charges</td><td>4</td><td>(12,712)</td><td>(6,157)</td></tr><tr><td>(Loss)/profit on ordinary activities before taxation</td><td>3</td><td>(109,006)</td><td>12,465</td></tr><tr><td>Tax on (loss)/profit on ordinary activities</td><td>5</td><td>5,450</td><td>(4,295)</td></tr><tr><td>(Loss)/profit on ordinary activities after taxation</td><td></td><td>(103,556)</td><td>8,170</td></tr></table>
