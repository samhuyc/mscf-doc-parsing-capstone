"""Reference-independent numeric inventory scoring; never repairs from labels."""
from collections import Counter
from decimal import Decimal
from html import unescape
import re
import unicodedata


def visible_text(text):
    text=re.sub(r'<[^>]*>', ' ', text)
    text=unescape(text)
    text=re.sub(r'\\(?:multirow|multicolumn)\{[^}]*\}\{[^}]*\}', ' ', text)
    text=re.sub(r'\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?', ' ', text)
    text=re.sub(r'\\[a-zA-Z]+', ' ', text)
    return text.replace('\\','').replace('|',' ').replace('*','')


def numbers(text):
    # Superscript notes are separate visible numbers, not appended value digits.
    text=re.sub('[⁰¹²³⁴⁵⁶⁷⁸⁹]+', lambda m:' '+unicodedata.normalize('NFKC',m[0])+' ', visible_text(text))
    text=unicodedata.normalize('NFKC',text).replace('−','-').replace('–','-').replace('—','-')
    text=re.sub(r'(?i)(\d{1,2})\s*(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s*(\d{4})(?!\d)', r'\1 \2 \3',text)
    text=re.sub(r'(?<=\d)-(?=\d)', ' ', text)  # Ranges, not negative amounts.
    # Space after a currency symbol must not turn accounting parentheses positive.
    text=re.sub(r'[$£€](?=\s*[+-]?\d)', '',text)
    pattern=r'(?<![\w.])(?P<open>\()?\s*(?P<sign>[+-]?)(?P<value>\d{1,3}(?:,\s*\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<unit>\s*(?:%|pts?|bn|m|k))?(?P<close>\s*\))?(?![\w.])'
    out=[]
    for m in re.finditer(pattern,text):
        value=Decimal(re.sub(r'[,\s]','',m['value']))
        if m['sign']=='-' or (m['open'] and m['close']): value=-value
        canonical=format(value.normalize(),'f')
        if value==0: canonical='0'
        unit=(m['unit'] or '').strip()
        out.append(canonical+('pts' if unit in ('pt','pts') else unit))
    return out


def numeric_score(reference, predicted):
    expected,actual=Counter(reference),Counter(predicted)
    matched=sum((expected&actual).values()); n=sum(expected.values()); m=sum(actual.values())
    if not n:raise ValueError('Numeric reference cannot be empty')
    return dict(reference_numbers=n,predicted_numbers=m,matched_numbers=matched,
                precision=matched/m if m else 0.,recall=matched/n,
                f1=2*matched/(n+m),exact=expected==actual,
                missing=list((expected-actual).elements()),extra=list((actual-expected).elements()))
