"""Initial source-image transcriptions by the assistant, 2026-10-05.

No parser predictions are consumed. Run once to create labels.jsonl; subsequent
human edits belong in labels.jsonl. Refuses to overwrite that file.
"""
from benchmark import ROOT, SOURCE, read_json, write_jsonl

sources = {s['id']: s for s in read_json(SOURCE/'source_manifest.json')}
labels = []


def add(doc, page, kind, name, region, **fields):
    label = dict(id=f'{doc}.p{page}.{name}', document=doc, page=page, kind=kind,
                 source_sha256=sources[doc]['sha256'], importance='critical' if kind in {'table','visual_fact'} else 'supporting',
                 review_status='draft', annotator='Codex assistant', reviewer=None, reviewed_at=None,
                 evidence=dict(region=region, basis='Original PDF page rendered and visually inspected in this chat'),
                 annotation_date='2026-10-05', **fields)
    labels.append(label)
    return label


def table(doc, page, name, region, columns, rows, units, **extra):
    return add(doc, page, 'table', name, region, columns=[dict(header_path=p) for p in columns],
               rows=[dict(label=n, values=v) for n,v in rows], unit_evidence=units,
               coverage=extra.pop('coverage', 'selected_rows'), **extra)


def text(doc, page, name, region, value):
    return add(doc, page, 'text', name, region, text=value)


def order(doc, page, name, before, after):
    return add(doc, page, 'reading_order', name, 'Named source blocks; only this pair has a required order', before=before, after=after)


def meta(doc, field, value, evidence):
    add(doc, 1, 'metadata', 'metadata_'+field, 'Cover/title block', field=field, value=value, evidence_text=evidence)


table('cvs_2025q2',6,'quarter_results','Left-hand Quarter Results table; all five data rows',
      [['2Q 2025'],['2Q 2024']], [
          ('Total Revenues',['$98.9','$91.2']),
          ('Adjusted Operating Income',['$3.81','$3.74']),
          ('GAAP Earnings per Share',['$0.80','$1.41']),
          ('Adjusted Earnings per Share',['$1.81','$1.83']),
          ('Cash Flow from Operations',['$1.9','$3.1'])],
      ['In billions, except per share amounts'], coverage='complete_data_matrix',
      context=dict(entity='CVS Health', currency='USD', scale='billions except EPS in dollars per share',
                   accounting_basis='Explicit GAAP/Adjusted qualifiers are part of row labels'))
text('cvs_2025q2',1,'title','Central title','Earnings Conference Call')
text('cvs_2025q2',6,'dividend','Right-hand bottom business-highlight paragraph',
     'Returned $866 million to stockholders through our quarterly dividend.')
add('cvs_2025q2',12,'footnote','prescription_note','Footnote 1',
    text='Includes an adjustment to convert 90-day prescriptions to the equivalent of three 30-day prescriptions.',
    marker='1', target=dict(description='90-day prescription adjustment; target links on other slides not annotated'))
order('cvs_2025q2',6,'order_title_table','Consolidated Results','Total Revenues')
order('cvs_2025q2',12,'order_notes','Includes an adjustment','Same store sales and prescription volume')
meta('cvs_2025q2','issuer','CVS Health','CVS Health')
meta('cvs_2025q2','reporting_period','2025-Q2','Second Quarter 2025')
meta('cvs_2025q2','document_type','earnings_presentation','Earnings Conference Call')

table('edf_2024',3,'segment_statement','Main table: selected total revenue, EBITDA, EBIT rows',
      [['Electricity supply','Domestic'],['Electricity supply','Non Domestic'],
       ['Gas supply','Domestic'],['Gas supply','Non Domestic'],['Aggregate supply business']], [
          ('Total revenue',['3,037.1','8,674.9','1,693.1','126.6','13,531.6']),
          ('EBITDA',['174.9','192.7','(84.6)','10.4','293.4']),
          ('EBIT',['164.2','150.1','(92.0)','6.4','228.7'])], ["£'M"],
      header_spans=[dict(text='Electricity supply',colspan=2),dict(text='Gas supply',colspan=2)],
      context=dict(entity='EDF supply business',period='year ended 31 December 2024',currency='GBP',scale='million'))
table('edf_2024',6,'reconciliation','Reconciliation table: all five named numeric data rows, excluding section heading',
      [['Revenue'],['EBIT']], [
          ('EDF Supply CSS',['13,531.6','228.7']),
          ('Non-licensed activities',['120.6','213.4']),
          ('Impairment of non-current assets',['-','(25.9)']),
          ('Restructuring costs',['-','(9.8)']),
          ('EDF Energy Customers Limited Statutory Accounts',['13,652.2','406.4'])], ["£'m"],
      coverage='complete_data_matrix', context=dict(entity='EDF Energy Customers Limited',period='2024',currency='GBP',scale='million'))
add('edf_2024',3,'footnote','sign_note','Second bullet under Notes',
    text='EBITDA and EBIT: positive figures indicate profit; negative figures indicate loss',
    marker=None, target=dict(table='edf_2024.p3.segment_statement',rows=['EBITDA','EBIT']))
text('edf_2024',6,'reconciliation_intro','Paragraph above table',
     'The table below shows how the CSS reconciles with EBIT in EDF Energy Customers Limited’s Income Statement for the year ended 31st December 2024:')
order('edf_2024',6,'order_table_notes','RECONCILIATION TO STATUTORY ACCOUNTS','Notes on reconciling items:')
meta('edf_2024','issuer','EDF','EDF')
meta('edf_2024','reporting_period','2024-12-31','year ended 31 December 2024')
meta('edf_2024','document_type','consolidated_segmental_statement','Consolidated Segmental Statement')

table('hippodrome_2025',20,'income_statement','Statement of comprehensive income: all eleven financial rows; Notes column is not data',
      [['2025'],['2024']], [
          ('Turnover',['116,787,681','114,583,476']),
          ('Cost of sales',['(49,553,722)','(49,669,638)']),
          ('Gross profit',['67,233,959','64,913,838']),
          ('Administrative expenses',['(61,723,344)','(56,732,754)']),
          ('Operating profit',['5,510,615','8,181,084']),
          ('Interest receivable and similar income',['913,167','1,000,725']),
          ('Interest payable and similar expenses',['(2,809,776)','(3,288,591)']),
          ('Other gains and losses',['169,884','8,941,676']),
          ('Profit before taxation',['3,783,890','14,834,894']),
          ('Tax on profit',['(1,056,033)','(2,349,942)']),
          ('Profit for the financial year',['2,727,857','12,484,952'])], ['£'],
      coverage='complete_data_matrix',context=dict(entity='Hippodrome Casino Limited',currency='GBP',scale='ones',period='year ended 31 December'))
table('hippodrome_2025',21,'financial_position','Selected rows of statement of financial position; year headers cover detail and total columns',
      [['2025'],['2024']], [
          ('Tangible assets',['49,022,342','47,854,347']),
          ('Net assets',['41,961,225','39,233,368']),
          ('Total equity',['41,961,225','39,233,368'])], ['£'],
      context=dict(entity='Hippodrome Casino Limited',currency='GBP',scale='ones',period='31 December'),
      review_note='Year groups cover multiple subcolumns. Ambiguous flattened exports must be reviewed; do not force a match.')
text('hippodrome_2025',20,'statement_title','Title above income statement','STATEMENT OF COMPREHENSIVE INCOME')
order('hippodrome_2025',20,'income_row_order','Turnover','Profit for the financial year')
meta('hippodrome_2025','issuer','Hippodrome Casino Limited','HIPPODROME CASINO LIMITED')
meta('hippodrome_2025','reporting_period','2025-12-31','31 DECEMBER 2025')
meta('hippodrome_2025','document_type','annual_accounts','REPORT AND FINANCIAL STATEMENTS')

table('peterborough_2025',2,'balance_sheet','Selected balance-sheet rows, including negative creditors and comparative values',
      [['2025'],['2024']], [
          ('Tangible assets',['967,756','992,467']),
          ('Bank and cash balances',['2,751,541','821,700']),
          ('Creditors: amounts falling due within one year',['(504,045)','(508,936)']),
          ('Net current assets',['4,526,437','5,249,019']),
          ('Net assets',['4,484,956','5,194,638']),
          ('Called up share capital',['130','130'])], ['£'],
      context=dict(entity='Peterborough Care Limited',currency='GBP',scale='ones',period='31 March'))
text('peterborough_2025',3,'audit_exemption','First paragraph below continued balance-sheet title',
     'The directors consider that the company is entitled to exemption from audit under section 477 of the Companies Act 2006 and members have not required the company to obtain an audit for the year in question in accordance with section 476 of the Companies Act 2006.')
text('peterborough_2025',3,'income_omission','Fifth paragraph, above approval statement',
     "The company has opted not to file the statement of comprehensive income in accordance with provisions applicable to companies subject to the small companies' regime.")
add('peterborough_2025',3,'footnote','notes_reference','Final sentence above page footer',
    text='The notes on pages 3 to 10 form part of these financial statements.', marker=None,
    target=dict(description='Printed pages 3–10; physical PDF pages 4–11. Cross-page links require review.'))
order('peterborough_2025',3,'audit_before_approval','The directors consider','The financial statements were approved')
meta('peterborough_2025','issuer','Peterborough Care Limited','PETERBOROUGH CARE LIMITED')
meta('peterborough_2025','reporting_period','2025-03-31','31 MARCH 2025')
meta('peterborough_2025','document_type','unaudited_financial_statements','UNAUDITED FINANCIAL STATEMENTS')

table('rolls_royce_2026h1_presentation',9,'underlying_results','Top-left table, all five rows and all four data columns',
      [['H1 2026'],['H1 2025'],['Organic Change'],['Organic Change %']], [
          ('Revenue',['11,279','9,057','2,310','26%']),
          ('Gross profit',['3,397','2,572','839','33%']),
          ('Gross margin %',['30.1%','28.4%','1.6pts','']),
          ('Operating profit',['2,534','1,733','796','46%']),
          ('Operating margin %',['22.5%','19.1%','3.1pts',''])], ['£m'],
      coverage='complete_data_matrix', context=dict(entity='Rolls-Royce Group',accounting_basis='underlying',currency='GBP',scale='million except ratios and percentage-point changes'))
table('rolls_royce_2026h1_presentation',9,'cash_results','Bottom-left table: free cash flow and net cash rows only',
      [['H1 2026'],['H1 2025'],['Change']], [
          ('Free cash flow',['1,964','1,582','382']),
          ('Net cash',['2,136','1,084','1,052'])], ['£m'],
      context=dict(entity='Rolls-Royce Group',currency='GBP',scale='million'))
for name,value,next_label in [('Operating profit','£2.5bn','Operating margin'),
                               ('Operating margin','22.5%','Free cash flow'),
                               ('Free cash flow','£2.0bn','Return on capital'),
                               ('CIVIL AEROSPACE','25.3%','DEFENCE'),
                               ('DEFENCE','21.0%','POWER SYSTEMS')]:
    add('rolls_royce_2026h1_presentation',5,'visual_fact','card_'+name.lower().replace(' ','_'),
        'Named metric card or divisional-margin panel',label=name,value=value,next_label=next_label,
        context=dict(period='H1 2026',basis='underlying for operating profit and margin'),
        review_note='Next label bounds a proposed text-sequence diagnostic, not a required global reading order.')
add('rolls_royce_2026h1_presentation',5,'footnote','underlying_note','Bottom-left footnote 1',
    text='Operating profit and operating margin shown on an underlying basis',marker='1',
    target=dict(description='Operating profit and operating margin cards'))
text('rolls_royce_2026h1_presentation',1,'cover_title','Large left-hand title','HALF YEAR RESULTS')
order('rolls_royce_2026h1_presentation',9,'table_row_order','Gross profit','Gross margin %')
meta('rolls_royce_2026h1_presentation','issuer','Rolls-Royce','Rolls-Royce')
meta('rolls_royce_2026h1_presentation','reporting_period','2026-H1','2026')
meta('rolls_royce_2026h1_presentation','document_type','results_presentation','HALF YEAR RESULTS')

table('rolls_royce_2026h1_release',1,'group_results','Top five data rows of Half Year 2026 Group Results; basis and year both required',
      [['Underlying','H1 2026'],['Underlying','H1 2025'],['Statutory','H1 2026'],['Statutory','H1 2025']], [
          ('Revenue',['11,279','9,057','11,448','9,490']),
          ('Operating profit',['2,534','1,733','2,418','2,074']),
          ('Operating margin %',['22.5%','19.1%','21.1%','21.9%']),
          ('Profit before taxation',['2,495','1,689','1,931','4,841'])], ['£ million'],
      context=dict(entity='Rolls-Royce Group',currency='GBP',scale='million except ratios'),
      review_note='Basis and period may appear within one header cell; both must be present in order.')
table('rolls_royce_2026h1_release',13,'income_statement','Selected unique rows in main income statement; repeated profit-for-period row excluded',
      [['30 June 2026'],['30 June 2025']], [
          ('Revenue',['11,448','9,490']),
          ('Cost of sales',['(8,021)','(6,563)']),
          ('Operating profit',['2,418','2,074']),
          ('Gain arising on disposal of business',['–','679']),
          ('Taxation',['(316)','(433)'])], ['£m'],
      context=dict(entity='Rolls-Royce Group',accounting_basis='statutory',currency='GBP',scale='million',period='half-year ended 30 June'))
table('rolls_royce_2026h1_release',17,'cash_reconciliation','Selected unique rows in top reconciliation table only',
      [['30 June 2026'],['30 June 2025']], [
          ('Change in cash and cash equivalents',['240','538']),
          ('Movement in net cash',['201','692']),
          ('Net cash at 30 June',['2,136','1,084'])], ['£m'],
      context=dict(entity='Rolls-Royce Group',currency='GBP',scale='million'))
add('rolls_royce_2026h1_release',13,'footnote','financing_note','Footnote 4 below income statement',
    text='Included within net financing are fair value changes on derivative contracts. Further details can be found in notes 2, 4 and 16',
    marker='4', target=dict(description='Net financing (costs)/income row'))
text('rolls_royce_2026h1_release',17,'continuation_heading','Top heading',
     'Condensed consolidated cash flow statement continued')
order('rolls_royce_2026h1_release',13,'income_row_order','Revenue','Gross profit')
meta('rolls_royce_2026h1_release','issuer','Rolls-Royce Holdings plc','ROLLS-ROYCE HOLDINGS PLC')
meta('rolls_royce_2026h1_release','reporting_period','2026-H1','2026 Half Year Results')
meta('rolls_royce_2026h1_release','document_type','results_press_release','This announcement contains inside information')

if __name__ == '__main__':
    destination = ROOT/'labels.jsonl'
    if destination.exists():
        raise SystemExit('labels.jsonl already exists; edit it directly to preserve review history.')
    write_jsonl(destination, labels)
    print(f'Created {len(labels)} source-derived DRAFT label records.')
