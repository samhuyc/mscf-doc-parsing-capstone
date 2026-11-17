"""Independent assistant transcriptions from source images, never model outputs."""
from common import RUN,read,write
DATA={}
def grid(name,text):
 rows=[[c.strip() for c in line.split('|')] for line in text.strip('\n').splitlines()]
 width=max(map(len,rows));assert all(len(r)==width for r in rows),(name,[len(r) for r in rows])
 return dict(name=name,cells=rows)
def add(tid,*grids):DATA[tid]=list(grids)

add('nestle_fy2025_presentation_p063_t01',grid('Historical eight quarters','''Period|RIG %|Pricing %|OG %
Q1-2024|-2.0|3.4|1.4
Q2-2024|2.2|0.6|2.8
Q3-2024|1.3|0.6|1.9
Q4-2024|1.5|1.2|2.7
Q1-2025|0.7|2.1|2.8
Q2-2025|-0.4|3.3|3.0
Q3-2025|1.5|2.8|4.3
Q4-2025|1.3|2.8|4.0'''))
add('nestle_fy2025_presentation_p064_t01',grid('Q4-2025 operating segments','''|Q4-2025 sales|Q4-2025 sales|Q4-2025 sales|Q4-2025 sales
|Sales (CHF m)|RIG %|Pricing %|OG %
Zone AMS|9 188|1.3|2.4|3.7
Zone AOA|5 290|2.0|2.6|4.6
Zone EUR|4 796|0.2|4.2|4.4
Nestlé Health Science|1 702|1.9|-0.4|1.5
Nespresso|1 775|-0.6|4.8|4.2
Nestlé Waters & Premium Beverages|795|4.5|3.8|8.3
Other Businesses|75|5.4|0.4|5.8
Total Group|23 621|1.3|2.8|4.0'''))
add('nestle_fy2025_presentation_p066_t01',grid('Operating segments by quarter','''|2025 Performance|2025 Performance|2025 Performance|2025 Performance|2025 Performance|2025 Performance|2025 Performance|2025 Performance|2025 Performance
|Q1-25|Q1-25|Q1-25|Q2-25|Q2-25|Q2-25|H1-25|H1-25|H1-25
|RIG %|Pricing %|OG %|RIG %|Pricing %|OG %|RIG %|Pricing %|OG %
Zone AMS|0.1|1.7|1.9|-1.2|3.5|2.3|-0.5|2.7|2.1
North America|1.1|-1.0|0.1|0.2|0.4|0.5|0.6|-0.3|0.3
Latin America|-1.6|6.7|5.1|-3.9|9.8|5.9|-2.7|8.3|5.5
Zone AOA|0.7|2.4|3.1|-1.2|2.9|1.7|-0.3|2.6|2.4
AOA excluding Greater China|-0.3|3.8|3.5|0.5|4.7|5.2|0.1|4.2|4.3
Greater China|4.0|-2.3|1.7|-7.1|-3.1|-10.2|-1.5|-2.7|-4.2
Zone EUR|-0.6|3.0|2.4|0.2|4.5|4.7|-0.2|3.7|3.5
Nestlé Health Science|4.8|-0.7|4.2|1.9|0.8|2.7|3.3|0.1|3.4
Nespresso|2.6|3.2|5.7|1.4|4.4|5.8|2.0|3.8|5.8
Nestlé Waters & Premium Beverages|1.6|2.0|3.6|2.9|2.7|5.6|2.3|2.4|4.7
Other Businesses|3.9|2.5|6.4|-2.1|2.5|0.3|0.7|2.5|3.2
Total Group|0.7|2.1|2.8|-0.4|3.3|3.0|0.2|2.7|2.9'''))
add('nestle_fy2025_presentation_p070_t01',grid('Operating segments sales and profit','''|In CHF m|In CHF m|In CHF m|In CHF m|In CHF m|In CHF m|In CHF m
|Sales|Underlying Trading Operating Profit|Trading Operating Profit|Net other trading income/(expense)|Of which impairment of property, plant and equipment|Of which restructuring costs|Depreciation and amortization
Zone AMS|34 482|7 118|6 474|(644)|(259)|(52)|(1 258)
Zone AOA|20 553|4 254|3 985|(269)|(16)|(106)|(594)
Zone Europe|17 581|2 834|2 600|(234)|(82)|(98)|(776)
Nestlé Health Science|6 551|1 056|709|(347)|(1)|(4)|(296)
Nespresso|6 481|1 160|1 136|(24)|(11)|(11)|(292)
Nestlé Waters & Premium Beverages|3 548|322|199|(123)|(69)|(1)|(157)
Other Businesses|294|6|(15)|(21)|(1)|-|(36)
Unallocated items|-|(2 361)|(2 413)|(52)|(4)|(34)|(224)
Total Group|89 490|14 389|12 675|(1 714)|(443)|(306)|(3 633)'''))

add('unilever_fy2025_release_p005_t01',grid('Business groups','''|Full Year 2025|Full Year 2025|Full Year 2025|Full Year 2025|Full Year 2025|Full Year 2025|Fourth Quarter 2025|Fourth Quarter 2025|Fourth Quarter 2025|Fourth Quarter 2025
(unaudited)|Turnover|USG|UVG|UPG|UOM|Change in UOM|Turnover|USG|UVG|UPG
Unilever|€50.5bn|3.5%|1.5%|2.0%|20.0%|60bps|€12.6bn|4.2%|2.1%|2.0%
Beauty & Wellbeing|€12.8bn|4.3%|2.2%|2.1%|19.2%|(20)bps|€3.2bn|4.7%|2.8%|1.8%
Personal Care|€13.2bn|4.7%|1.1%|3.6%|22.6%|50bps|€3.3bn|5.1%|0.6%|4.5%
Home Care|€11.6bn|2.6%|2.2%|0.4%|14.9%|40bps|€2.8bn|4.7%|4.0%|0.6%
Foods|€12.9bn|2.5%|0.8%|1.7%|22.6%|130bps|€3.3bn|2.3%|1.3%|1.0%'''))
add('unilever_fy2025_release_p005_t02',grid('Beauty and wellbeing','''(unaudited)|Turnover|USG|UVG|UPG|A&D|Currency|Turnover change|UOM%|Change in UOM
Full Year|€12.8bn|4.3%|2.2%|2.1%|(0.6)%|(5.8)%|(2.3)%|19.2%|(20)bps
Fourth Quarter|€3.2bn|4.7%|2.8%|1.8%|0.5%|(8.4)%|(3.7)%||'''))
geo_head='''|Full Year 2025|Full Year 2025|Full Year 2025|Full Year 2025|Fourth Quarter 2025|Fourth Quarter 2025|Fourth Quarter 2025|Fourth Quarter 2025
(unaudited)|Turnover|USG|UVG|UPG|Turnover|USG|UVG|UPG
'''
add('unilever_fy2025_release_p008_t01',grid('Geographical areas',geo_head+'''Unilever|€50.5bn|3.5%|1.5%|2.0%|€12.6bn|4.2%|2.1%|2.0%
Asia Pacific Africa|€22.4bn|4.6%|3.0%|1.6%|€5.5bn|6.9%|5.7%|1.2%
The Americas|€18.6bn|3.3%|–%|3.2%|€4.7bn|3.0%|(0.8)%|3.8%
Europe|€9.5bn|1.5%|1.2%|0.3%|€2.4bn|0.1%|(0.2)%|0.3%'''),grid('Market groups',geo_head+'''Emerging markets|€30.0bn|3.5%|0.8%|2.7%|€7.4bn|5.8%|3.2%|2.5%
Developed markets|€20.5bn|3.6%|2.6%|0.9%|€5.2bn|1.7%|0.5%|1.1%
North America|€11.2bn|5.3%|3.8%|1.4%|€2.8bn|2.8%|1.3%|1.5%
Latin America|€7.4bn|0.5%|(5.1)%|5.9%|€1.9bn|3.2%|(3.6)%|7.1%'''))
add('unilever_fy2025_release_p014_t01',grid('Non-underlying items','''€ million|Full Year|Full Year
(unaudited)|2025|2024
Non-underlying items within operating profit before tax|(1,047)|(1,369)
Acquisition and disposal-related costs|(288)|(293)
Gain on disposal of group companies|(36)|(229)
Restructuring costs|(599)|(710)
Impairments|(43)|(134)
Other|(81)|(3)
Tax on non-underlying items within operating profit|7|88
Non-underlying items within operating profit after tax|(1,040)|(1,281)
Non-underlying items not in operating profit but within net profit before tax|(34)|(167)
Interest related to non-underlying items|34|35
Net monetary loss arising from hyperinflationary economies|(68)|(201)
Tax impact of non-underlying items not in operating profit but within net profit, including non-underlying tax items|(39)|85
Non-underlying items not in operating profit but within net profit after tax|(73)|(82)
Non-underlying items after tax|(1,113)|(1,363)
Attributable to:||
Non-controlling interests|(34)|22
Shareholders’ equity|(1,079)|(1,385)'''))
add('unilever_fy2025_release_p014_t02',grid('Operating profit reconciliation','''€ million|Full Year|Full Year
(unaudited)|2025|2024
Operating profit|9,037|8,829
Non-underlying items within operating profit|1,047|1,369
Underlying operating profit|10,084|10,198
Turnover|50,503|52,479
Operating margin (%)|17.9|16.8
Underlying operating margin (%)|20.0|19.4'''))
add('unilever_fy2025_release_p020_t01',grid('Consolidated income statement','''€ million|Full Year|Full Year|Full Year
(unaudited)|2025|2024|Change
Turnover|50,503|52,479|(3.8)%
Operating profit|9,037|8,829|2.4%
Net finance costs|(503)|(520)|
Pensions and similar obligations|123|83|
Finance income|398|391|
Finance costs|(1,024)|(994)|
Net monetary loss arising from hyperinflationary economies|(68)|(201)|
Share of net profit of joint ventures and associates|245|250|
Other income/(loss) from non-current investments and associates|(17)|13|
Profit before taxation from continuing operations|8,693|8,371|3.9%
Taxation|(2,481)|(2,332)|
Net profit from continuing operations|6,213|6,039|2.9%
Profit after taxation from discontinued operations|425|330|
Gain on disposal of discontinued operation|3,373|–|
Net profit from discontinued operations|3,798|330|
Total net profit|10,011|6,369|
Attributable to:|||
Non-controlling interests|542|625|
Shareholders’ equity|9,469|5,744|64.9%
Total profit attributable to shareholders’ equity arises from:|||
Continuing operations|5,682|5,430|
Discontinued operations|3,787|314|
Total profit attributable to non-controlling interests arises from:|||
Continuing operations|531|609|
Discontinued operations|11|16|
Earnings per share|||
Basic earnings per share (euros)|4.33|2.59|67.0%
Basic earnings per share (€) from continuing operations|2.60|2.45|6.1%
Basic earnings per share (€) from discontinued operations|1.73|0.14|1124.3%
Diluted earnings per share (euros)|4.32|2.58|67.6%
Diluted earnings per share (€) from continuing operations|2.59|2.44|6.2%
Diluted earnings per share (€) from discontinued operations|1.73|0.14|1125.1%'''))

add('harrods_fy2025_accounts_p022_t01',grid('Profit and loss','''|Note|52 weeks ended 1 February 2025 £ m|53 weeks ended 3 February 2024 £ m
Turnover|3|894.6|898.4
Cost of sales||(343.6)|(341.8)
Gross profit||551.0|556.6
Distribution costs||(379.6)|(362.2)
Administrative expenses||(87.2)|(73.5)
Other operating income|4|42.7|42.3
Fair value movement||0.4|(0.3)
Operating profit before pensions loss on settlement and exceptional items||127.3|162.9
Pensions loss on settlement|21|-|(35.9)
Exceptional items|5|(77.7)|-
Operating profit after pensions loss on settlement and exceptional items||49.6|127.0
Income from shares in group companies|9|1.0|-
Interest receivable and similar income|10|37.0|38.2
Interest payable and similar charges|11|(2.5)|(3.0)
Profit before tax||85.1|162.2
Taxation|12|(24.6)|(40.1)
Profit for the financial period||60.5|122.1'''))
add('harrods_fy2025_accounts_p023_t01',grid('Other comprehensive income','''|Note|52 weeks ended 1 February 2025 £ m|53 weeks ended 3 February 2024 £ m
Profit for the period||60.5|122.1
Actuarial gains on defined benefit pension scheme|21|2.9|0.9
Movement of deferred tax relating to pension surplus|12|(0.7)|(0.2)
Other comprehensive gain for the period||2.2|0.7
Total comprehensive income for the period||62.7|122.8'''))
add('harrods_fy2025_accounts_p024_t01',grid('Balance sheet','''|Note|1 February 2025 £ m|3 February 2024 £ m
Fixed assets|||
Intangible assets|13|6.0|16.4
Tangible assets|14|1,479.2|1,458.2
Investments|15|225.1|225.1
||1,710.3|1,699.7
Current assets|||
Stocks|16|99.0|105.5
Debtors: amounts falling due after more than one year|17|-|2.9
Debtors: amounts falling due within one year|17|839.7|812.5
Cash at bank and in hand||76.6|50.8
||1,015.3|971.7
Creditors: Amounts falling due within one year|18|(475.3)|(380.9)
Net current assets||540.0|590.8
Total assets less current liabilities||2,250.3|2,290.5
Creditors: Amounts falling due after more than one year|18|(3.0)|(2.3)
Net assets excluding pension asset||2,247.3|2,288.2
Pension asset|21|44.3|40.7
Net assets||2,291.6|2,328.9
Capital and reserves|||
Called up share capital|20|19.2|19.2
Share premium reserve|20|921.0|921.0
Revaluation reserve|20|0.4|0.4
Profit and loss account||1,351.0|1,388.3
Total equity||2,291.6|2,328.9'''))
add('harrods_fy2025_accounts_p026_cash_flow',grid('Cash flows','''|52 weeks ended 1 February 2025 £ m|53 weeks ended 3 February 2024 £ m
Cash flows from operating activities||
Profit for the period|60.5|122.1
Adjustments to cash flows from non-cash items||
Depreciation and amortisation|59.9|58.8
Finance income|(37.0)|(38.2)
Finance costs|2.5|3.0
Income tax expense|24.6|40.1
Income from subsidiaries|(1.0)|-
Assets written off|7.0|0.6
Fair value movement|(0.4)|0.3
Pensions loss on settlement|-|35.9
Non-cash exceptional costs|63.3|-
Scheme administration expenses|1.3|2.0
|180.7|224.6
Working capital and other adjustments||
Decrease/(increase) in stocks|6.5|(15.9)
(Increase) / decrease in debtors|(2.1)|61.4
Increase / (decrease) in creditors|7.1|(4.8)
Cash generated from operations|192.2|265.3
Corporation taxes paid|(29.4)|(41.6)
Net cash flow from operating activities|162.8|223.7
Cash flows from investing activities||
Acquisitions of tangible and intangible assets|(71.9)|(60.2)
Interest received|35.0|35.9
Net cash flows from investing activities|(36.9)|(24.3)
Cash flows from financing activities||
Dividends paid|(100.0)|(180.0)
Interest paid|(0.1)|(2.0)
Net cash flows from financing activities|(100.1)|(182.0)
Net increase in cash and cash equivalents|25.8|17.4
Cash and cash equivalents at 3 February 2024|50.8|33.4
Cash and cash equivalents at 1 February 2025|76.6|50.8'''))
add('dyson_2024_accounts_p028_t01',grid('Comprehensive income','''|Note|2024 £ m|2023 £ m
Turnover|5|305.0|358.2
Cost of sales||(247.4)|(292.8)
Gross Profit||57.6|65.4
Distribution costs||(2.0)|(2.4)
Administrative expenses||(48.1)|(54.3)
Operating Profit|6|7.5|8.7
Finance income|10|1.1|0.6
Finance costs|11|(2.2)|(1.5)
Profit before tax||6.4|7.8
Tax on Profit|12|(1.7)|(3.3)
Profit for the financial year||4.7|4.5'''))
add('dyson_2024_accounts_p029_t01',grid('Balance sheet','''||2024 £ m|2023 £ m
Fixed assets|||
Intangible assets|13|-|-
Tangible assets|14|2.3|3.1
Investments|15|32.2|32.2
||34.5|35.3
Current assets|||
Inventories|16|23.5|27.9
Debtors: amounts falling due within one year|17|178.1|116.8
Cash at bank and in hand||-|-
||201.6|144.7
Creditors: amounts falling due within one year|18|(170.4)|(117.5)
Net current assets||31.2|27.2
Total assets less current liabilities||65.7|62.5
Provisions for liabilities|19|(12.5)|(14.0)
Net assets||53.2|48.5
Capital and reserves|||
Called-up share capital|20|-|-
Retained earnings||53.2|48.5
Total equity||53.2|48.5'''))
add('dyson_2024_accounts_p030_t01',grid('Changes in equity','''|Called-up share capital £ m|Retained earnings £ m|Total equity £ m
At 1 January 2023|-|44.0|44.0
Profit for the year|-|4.5|4.5
At 31 December 2023 and At 1 January 2024|-|48.5|48.5
Profit for the year|-|4.7|4.7
At 31 December 2024|-|53.2|53.2'''))

def main():
 bundle=read(RUN/'fresh_public/tables.json');index={t['table_id']:t for t in bundle['tables']};refs={}
 for tid,grids in DATA.items():
  table=index[tid]
  refs[tid]=dict(table_id=tid,issuer=table['issuer'],grids=grids,human_verified=False,reference_kind='assistant_source_checked',
                source_sha256=table['source_sha256'],image_sha256=table['image_sha256'],basis='Direct visual transcription from the source crop before inspecting fresh model output.')
 write(RUN/'fresh_public/references.json',refs);print('Source-checked fresh references:',len(refs),'/',len(index))
if __name__=='__main__':main()
