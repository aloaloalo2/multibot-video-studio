"""Read-only character comparison with recognized number expressions in digit form.

No source text, narration cache key, price or timing is changed here.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from functools import lru_cache

import number_text

SUPPORTED = {'en', 'uk', 'ru', 'de', 'es', 'pl', 'fr', 'it', 'pt', 'nl', 'da'}
WORDS = re.compile(r"[^\W\d_]+(?:[-’ʼ'][^\W\d_]+)*|\d+(?:[.,]\d+)*|[^\w\s]", re.UNICODE)
DIGITS = re.compile(r"(?<!\w)\d+(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|(?<!\w)\d+(?:[.,]\d+)*(?:/\d+)?(?:st\b|nd\b|rd\b|th\b|-(?:го|му|ми|й|я|е|ю|м|х|а|у)\b)?")
SCALES = {'en':{'thousand':1000,'million':10**6,'billion':10**9},
          'es':{'mil':1000,'millón':10**6,'millones':10**6},
          'pl':{'tysiąc':1000,'tysiące':1000,'tysięcy':1000,'milion':10**6,'milionów':10**6,'miliony':10**6},
          'uk':{'тисяча':1000,'тисячі':1000,'тисяч':1000,'мільйон':10**6,'мільйони':10**6,'мільйонів':10**6},
          'ru':{'тысяча':1000,'тысячи':1000,'тысяч':1000,'миллион':10**6,'миллиона':10**6,'миллионов':10**6}}


def decimal_text(value):
    value=format(Decimal(str(value)), 'f')
    return value.rstrip('0').rstrip('.') if '.' in value else value


def digit_value(text, language):
    value = re.sub(r'[ \u00a0\u202f]', '', text)
    value = re.sub(r'(?:st|nd|rd|th|-(?:го|му|ми|й|я|е|ю|м|х|а|у))$','',value)
    if '/' in value:
        return value
    # Group separators and decimal marks follow the language's written convention.
    thousands = ',' if language == 'en' else '.'
    if re.fullmatch(r'\d{1,3}(?:' + re.escape(thousands) + r'\d{3})+(?:[.,]\d+)?', value):
        value = value.replace(thousands, '')
    value = value.replace(',', '.')
    try:
        return decimal_text(Decimal(value))
    except ArithmeticError:
        return text  # Ambiguous formatting is retained, never guessed.


def slavic_spans(text, language):
    """Polish cardinal/declined numbers and Ukrainian compound ordinal years."""
    if language == 'uk':
        cardinal, scales = number_text.CARDINAL, number_text.SCALE
        roots = {'перш': 1, 'друг': 2, 'трет': 3, 'четверт': 4, "п'ят": 5, 'шост': 6,
                 'сьом': 7, 'восьм': 8, "дев'ят": 9, 'десят': 10, 'одинадцят': 11,
                 'дванадцят': 12, 'тринадцят': 13, 'чотирнадцят': 14, "п'ятнадцят": 15,
                 'шістнадцят': 16, 'сімнадцят': 17, 'вісімнадцят': 18, "дев'ятнадцят": 19,
                 'двадцят': 20, 'тридцят': 30, 'сороков': 40, "п'ятдесят": 50,
                 'шістдесят': 60, 'сімдесят': 70, 'вісімдесят': 80, "дев'яност": 90}
        endings = ('ий', 'ій', 'а', 'я', 'е', 'є', 'ого', 'ої', 'ому', 'им', 'ім', 'их', 'у')
    else:
        cardinal = {}
        rows = ['zero zera zeru zerem', 'jeden jedna jedno jednego jednej jedną jednym jednemu',
                'dwa dwie dwóch dwu dwóm dwoma dwiema', 'trzy trzech trzem trzema',
                'cztery czterech czterem czterema', 'pięć pięciu pięcioma', 'sześć sześciu sześcioma',
                'siedem siedmiu siedmioma', 'osiem ośmiu ośmioma', 'dziewięć dziewięciu dziewięcioma',
                'dziesięć dziesięciu dziesięcioma', 'jedenaście jedenastu', 'dwanaście dwunastu',
                'trzynaście trzynastu', 'czternaście czternastu', 'piętnaście piętnastu',
                'szesnaście szesnastu', 'siedemnaście siedemnastu', 'osiemnaście osiemnastu',
                'dziewiętnaście dziewiętnastu']
        for n, forms in enumerate(rows):
            cardinal.update(dict.fromkeys(forms.split(), n))
        for n, forms in [(20,'dwadzieścia dwudziestu'),(30,'trzydzieści trzydziestu'),
                         (40,'czterdzieści czterdziestu'),(50,'pięćdziesiąt pięćdziesięciu'),
                         (60,'sześćdziesiąt sześćdziesięciu'),(70,'siedemdziesiąt siedemdziesięciu'),
                         (80,'osiemdziesiąt osiemdziesięciu'),(90,'dziewięćdziesiąt dziewięćdziesięciu'),
                         (100,'sto stu'),(200,'dwieście dwustu'),(300,'trzysta trzystu'),
                         (400,'czterysta czterystu'),(500,'pięćset pięciuset'),(600,'sześćset sześciuset'),
                         (700,'siedemset siedmiuset'),(800,'osiemset ośmiuset'),(900,'dziewięćset dziewięciuset')]:
            cardinal.update(dict.fromkeys(forms.split(), n))
        scales = {}
        for n, forms in [(1000,'tysiąc tysiące tysięcy tysiąca tysiącem tysiącom'),
                         (1000000,'milion miliony milionów miliona milionem'),
                         (1000000000,'miliard miliardy miliardów miliarda')]:
            scales.update(dict.fromkeys(forms.split(), n))
        roots = dict(zip(('pierwsz','drug','trzec','czwart','piąt','szóst','siódm','ósm','dziewiąt','dziesiąt',
                         'jedenast','dwunast','trzynast','czternast','piętnast','szesnast','siedemnast','osiemnast','dziewiętnast'),range(1,20)))
        roots.update({'dwudziest':20,'trzydziest':30,'czterdziest':40,'pięćdziesiąt':50,
                      'sześćdziesiąt':60,'siedemdziesiąt':70,'osiemdziesiąt':80,'dziewięćdziesiąt':90,'setn':100})
        endings = ('y','i','a','e','ego','ej','emu','ym','im','ych','ich','ą')
    ordinals = {root+end: value for root,value in roots.items() for end in endings}
    if language=='uk':
        ordinals.update(dict.fromkeys(('третій','третя','третє','третього','третьої','третьому','третьою','третьої','третіх','третім'),3))
    tokens = list(WORDS.finditer(text)); result=[]; i=0
    while i<len(tokens):
        start=i; group=total=0; last=None; has_ordinal=False
        while i<len(tokens):
            word=number_text.fold(tokens[i].group())
            if i>start:
                separator=text[tokens[i-1].end():tokens[i].start()]
                if not separator.isspace() or '\n' in separator:break
            value=cardinal.get(word); ordinal=ordinals.get(word); scale=scales.get(word)
            compound_year=language=='uk' and bool(re.fullmatch(r'дво(?:х)?тисячн(?:ий|ого|ому|им|ім|а|ої|ій|ою|е)',word))
            if value is None and ordinal is not None:value=ordinal
            if compound_year and i==start:
                total=2000;group=0;last=None;has_ordinal=True
            elif scale is not None:
                total+=(group or 1)*scale;group=0;last=None
            elif value is not None:
                if last is not None and (last<20 or (last<100 and value>=10) or (last>=100 and value>=100)):break
                group+=value;last=value
            else:break
            i+=1
            if ordinal is not None:
                has_ordinal=True
                if value%10 or value>=100:break
        if i>start:
            if language=='pl' or has_ordinal:
                result.append((tokens[start].start(),tokens[i-1].end(),str(total+group)))
        else:i+=1
    return result


def latin_spans(text, language):
    from text_to_num import Token, find_numbers
    matches=list(WORDS.finditer(text))
    class Word(Token):
        def __init__(self, index):self.index=index
        def text(self):return matches[self.index].group()
        def not_a_number_part(self):
            return (language=='es' and self.text().lower()=='ciento' and self.index>0
                    and matches[self.index-1].group().lower()=='por')
        def nt_separated(self, previous):
            return '\n' in text[matches[previous.index].end():matches[self.index].start()]
    result=[]
    for number in find_numbers([Word(i) for i in range(len(matches))],language,threshold=0):
        a,b=matches[number.start].start(),matches[number.end-1].end()
        words=text[a:b].lower()
        # Single indefinite articles/pronouns are not a numerical fact.
        if words in {'un','una','unos','unas','une','um','uma','een'}:continue
        if words=='uno' and re.match(r'\s+de\b',text[b:],re.I):continue
        if language=='es' and words in {'miles','millones','billones'}:continue
        # Do not read a fraction denominator as a separate ordinal quantity.
        if language=='es' and (words in {'cuartos','tercios'} or re.match(r'\s+(?:cuartos|tercios)\b',text[b:],re.I)):
            continue
        value=decimal_text(number.value)
        if language=='es':
            scale=re.search(r'\b(mil|millón|millones)\Z',words)
            half=re.match(r'\s+y\s+medi[oa]\b',text[b:],re.I)
            half_scale=re.match(r'\s+y\s+medi[oa]\s+(mil|millón|millones)\b',text[b:],re.I)
            if scale and half:
                value=decimal_text(Decimal(value)+Decimal(SCALES['es'][scale[1]])/2)
                b+=half.end()
            elif half_scale:
                value=decimal_text((Decimal(value)+Decimal('.5'))*SCALES['es'][half_scale[1].lower()])
                b+=half_scale.end()
        result.append((a,b,value))
    return result


@lru_cache(maxsize=64)
def normalized(text: str, language: str):
    """Return display-only text and recognized numeral spans, retaining all other words."""
    if language not in SUPPORTED:
        return text, (), False
    if language in {'en','ru','uk','de'}:
        spans=[]
        for a,b,value in number_text.replacements(text,language):
            match=re.fullmatch(r'(\d+(?:[.,]\d+)?(?:/\d+)?)(?:st|nd|rd|th|-[^\W\d_]+|\.)?',value)
            if match:spans.append((a,b,digit_value(match[1],language)))
        if language=='uk':spans+=slavic_spans(text,language)
        if language=='en':
            try:spans += [s for s in latin_spans(text,language) if '-' in text[s[0]:s[1]]]
            except ImportError:pass
    elif language=='pl':spans=slavic_spans(text,language)
    else:
        try:spans=latin_spans(text,language)
        except ImportError:return text, (), False
    for match in DIGITS.finditer(text):
        value=digit_value(match.group(),language)
        end=match.end()
        scale=re.match(r'[\s-]+([^\W\d_]+)',text[end:])
        multiplier=SCALES.get(language,{}).get(scale[1].lower()) if scale else None
        if multiplier:
            try:value=decimal_text(Decimal(value)*multiplier);end+=scale.end()
            except ArithmeticError:pass
        spans.append((match.start(),end,value))
    # A full compound year supersedes a shorter cardinal prefix.
    kept=[];end=-1
    for span in sorted(spans,key=lambda x:(x[0],-x[1])):
        if span[0]>=end:kept.append(span);end=span[1]
    # Polish separates the integer and fractional part with an explicit word.
    if language=='pl':
        decimals=[]
        for span in kept:
            if (decimals and text[decimals[-1][1]:span[0]].strip().lower() in {'przecinek','koma'}
                    and decimals[-1][2].isdigit() and span[2].isdigit()):
                a,_,value=decimals.pop();decimals.append((a,span[1],value+'.'+span[2]))
            else:decimals.append(span)
        kept=decimals
    rendered=text
    for a,b,value in reversed(kept):rendered=rendered[:a]+value+rendered[b:]
    return rendered,tuple(kept),True


def paired_forms(source: str, translated: str, source_language: str, target_language: str):
    """Discount only a source digit paired with the same value in target words.

    Match occurrences, not merely a set of values. Ordinary words and unmatched
    or changed quantities stay intact. The general parser above is still used
    separately for semantic year validation; it does not define display counts.
    """
    from collections import defaultdict, deque
    _, source_spans, source_ok = normalized(source, source_language)
    _, target_spans, target_ok = normalized(translated, target_language)
    available = source_ok and target_ok
    selected_source, selected_target = [], []
    source_digits=[span for span in source_spans if any(c.isdecimal() for c in source[span[0]:span[1]])]
    if available:
        digits = defaultdict(deque)
        for span in source_spans:
            if any(c.isdecimal() for c in source[span[0]:span[1]]):
                digits[span[2]].append(span)
        for span in target_spans:
            if (not any(c.isdecimal() for c in translated[span[0]:span[1]])
                    and digits[span[2]]):
                selected_source.append(digits[span[2]].popleft())
                selected_target.append(span)
    def render(text, spans):
        for a, b, value in sorted(spans, reverse=True):
            text = text[:a] + value + text[b:]
        return text
    return ((render(source, source_digits), tuple(sorted(selected_source)), available),
            (render(translated, selected_target), tuple(selected_target), available))


def comparison_chars(text: str) -> int:
    """Count Unicode letters only; numeric matching happens before this step.

    Apostrophe-like modifier letters are punctuation in narration. Never use
    this linguistic length metric for provider billing or API payload limits.
    """
    return sum(unicodedata.category(char).startswith('L') and char not in '\u02bc\u02bb' for char in text)


def source_comparison_chars(text, language, units=None):
    """Stable source letter basis independent of the selected target language."""
    def reduced(value):
        _,spans,ready=normalized(value,language)
        if not ready:return 0
        return sum(comparison_chars(value[a:b]) for a,b,_ in spans if any(c.isdecimal() for c in value[a:b]))
    return comparison_chars(text)-sum(reduced(value) for value in units) if units is not None else comparison_chars(text)-reduced(text)


def comparison(source: str, translated: str, source_language: str, target_language: str,
               *, source_units=None, translated_units=None) -> dict:
    if (source_units is not None and translated_units is not None
            and len(source_units) == len(translated_units)):
        # Whole-script counts ignore whitespace and punctuation. Matched
        # number discounts come only from the corresponding phrase, so a digit
        # in another sentence cannot hide an indefinite 'one' here.
        pairs = [paired_forms(a, b, source_language, target_language)
                 for a, b in zip(source_units, translated_units)]
        ready = source_language in SUPPORTED and target_language in SUPPORTED and all(a[2] and b[2] for a, b in pairs)
        source_reduction = sum(comparison_chars(text)-comparison_chars(pair[0][0]) for text, pair in zip(source_units, pairs))
        target_reduction = sum(comparison_chars(text)-comparison_chars(pair[1][0]) for text, pair in zip(translated_units, pairs))
        left_count, right_count = comparison_chars(source)-source_reduction, comparison_chars(translated)-target_reduction
        source_count = sum(len(a[1]) for a, _ in pairs)
        target_count = sum(len(b[1]) for _, b in pairs)
    else:
        (left, left_spans, ready), (right, right_spans, _) = paired_forms(source, translated, source_language, target_language)
        left_count, right_count = comparison_chars(left), comparison_chars(right)
        source_count, target_count = len(left_spans), len(right_spans)
        source_reduction, target_reduction = comparison_chars(source)-left_count, comparison_chars(translated)-right_count
    difference = right_count-left_count
    return {'available':ready,'source_language':source_language,'target_language':target_language,
            'source_chars':left_count if ready else None,'translated_chars':right_count if ready else None,
            'difference_chars':difference if ready else None,
            'difference_percent':round(100*difference/left_count,2) if ready and left_count else None,
            'source_numbers':source_count,'translated_numbers':target_count,
            'source_reduction':source_reduction,'translated_reduction':target_reduction,
            'basis':'source_digits_matched_to_target_words','punctuation_excluded':True,
            'spaces_included':False,'letters_only':True,'advisory_only':True}
