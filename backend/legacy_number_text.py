# -*- coding: utf-8 -*-
"""Frozen legacy number formatter, used only to recognize older saved plans.

Do not use this version to format new content: some words were misidentified
as numbers. Its exact behavior is needed to validate a safe in-memory upgrade.
"""
from __future__ import annotations
import re
import unicodedata
from fractions import Fraction

WORD = re.compile(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)*", re.UNICODE)
TOKEN = re.compile(r"[+-]?\d+(?:[.,]\d+)?(?:/\d+)?(?:-\d+(?:[.,]\d+)?)?(?:st|nd|rd|th|-(?:го|му|ми|й|я|е|ю|м|х|а|у))?|[^\W\d_]+", re.UNICODE)
CARDINAL = {}
SCALE = {}


def fold(value):
    return unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").replace("’", "'").replace("ʼ", "'").replace("–", "-")


def add(value, words, target=CARDINAL):
    for word in words.split():
        target[fold(word)] = value


for value, words in enumerate([
    "ноль нуль нуля нулю нулем zero null нулів", "один одна одно одни одного одной одну одному одним одном одних одними one ein eins eine einen einem einer eines одне одні однієї одній однією",
    "два две двух двум двумя two zwei двох двом двома дві", "три трех трем тремя three drei трьох трьом трьома",
    "четыре четырех четырем четырьмя four vier чотири чотирьох чотирьом чотирма", "пять пяти пятью five fünf п'ять п'яти п'ятьма",
    "шесть шести шестью six sechs шість шести шістьма", "семь семи семью seven sieben сім семи сімома",
    "восемь восьми восемью eight acht вісім восьми вісьмома", "девять девяти девятью nine neun дев'ять дев'яти дев'ятьма",
    "десять десяти десятью ten zehn", "одиннадцать одиннадцати eleven elf одинадцять одинадцяти",
    "двенадцать двенадцати twelve zwölf дванадцять дванадцяти", "тринадцать тринадцати thirteen dreizehn тринадцять тринадцяти",
    "четырнадцать четырнадцати fourteen vierzehn чотирнадцять чотирнадцяти", "пятнадцать пятнадцати fifteen fünfzehn п'ятнадцять п'ятнадцяти",
    "шестнадцать шестнадцати sixteen sechzehn шістнадцять шістнадцяти", "семнадцать семнадцати seventeen siebzehn сімнадцять сімнадцяти",
    "восемнадцать восемнадцати eighteen achtzehn вісімнадцять вісімнадцяти", "девятнадцать девятнадцати nineteen neunzehn дев'ятнадцять дев'ятнадцяти",
]):
    add(value, words)
for value, words in [
    (20,"двадцать двадцати twenty zwanzig двадцять двадцяти"),(30,"тридцать тридцати thirty dreißig тридцять тридцяти"),
    (40,"сорок сорока forty vierzig"),(50,"пятьдесят пятидесяти fifty fünfzig п'ятдесят п'ятдесяти"),
    (60,"шестьдесят шестидесяти sixty sechzig шістдесят шістдесяти"),(70,"семьдесят семидесяти seventy siebzig сімдесят сімдесяти"),
    (80,"восемьдесят восьмидесяти eighty achtzig вісімдесят вісімдесяти"),(90,"девяносто девяноста ninety neunzig дев'яносто дев'яноста"),
    (100,"сто ста hundred hundert"),(200,"двести двухсот двумстам двумястами двести двісті двохсот"),
    (300,"триста трехсот трьохсот"),(400,"четыреста четырехсот чотириста чотирьохсот"),
    (500,"пятьсот пятисот п'ятсот п'ятисот"),(600,"шестьсот шестисот шістсот шестисот"),
    (700,"семьсот семисот сімсот семисот"),(800,"восемьсот восьмисот вісімсот восьмисот"),(900,"девятьсот девятисот дев'ятсот дев'ятисот"),
    (2,"двое двоих двоим двома"),(3,"трое троих троим"),(4,"четверо четверых"),(5,"пятеро пятерых"),
    (6,"шестеро шестерых"),(7,"семеро семерых"),(8,"восьмеро восьмерых"),(9,"девятеро девятерых"),
]: add(value, words)
for value, words in [(1000,"тысяча тысячи тысяч тысячу тысячей тысяче thousand tausend тисяча тисячі тисяч тисячу"),
                     (1000000,"миллион миллиона миллионов million millions millionen мільйон мільйона мільйонів"),
                     (1000000000,"миллиард миллиарда миллиардов billion billions milliarde milliarden мільярд мільярда мільярдів")]: add(value,words,SCALE)

ORDINAL = {}
for value, word in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(),1):
    suffix = "th" if 10 <= value % 100 <= 20 else {1:"st",2:"nd",3:"rd"}.get(value%10,"th")
    ORDINAL[word] = (value,suffix)
for value, word in [(30,"thirtieth"),(40,"fortieth"),(50,"fiftieth"),(60,"sixtieth"),(70,"seventieth"),(80,"eightieth"),(90,"ninetieth"),(100,"hundredth"),(1000,"thousandth")]: ORDINAL[word]=(value,"th")
RU_ROOTS={"перв":1,"втор":2,"трет":3,"четверт":4,"пят":5,"шест":6,"седьм":7,"восьм":8,"девят":9,"десят":10,"одиннадцат":11,"двенадцат":12,"тринадцат":13,"четырнадцат":14,"пятнадцат":15,"шестнадцат":16,"семнадцат":17,"восемнадцат":18,"девятнадцат":19,"двадцат":20,"тридцат":30,"сороков":40,"пятидесят":50,"шестидесят":60,"семидесят":70,"восьмидесят":80,"девяност":90,"сот":100,"тысячн":1000}
ENDINGS={"ый":"й","ий":"й","ой":"й","ая":"я","ое":"е","ые":"е","ую":"ю","ого":"го","ому":"му","ым":"м","ом":"м","ых":"х","ыми":"ми","ей":"й","ья":"я","ье":"е","ью":"ю","ьего":"го","ьему":"му","ьим":"м","ьем":"м","ьих":"х","ьими":"ми"}
for root,value in RU_ROOTS.items():
    for ending,suffix in ENDINGS.items(): ORDINAL[root+ending]=(value,"-"+suffix)
for value,root in [(1,"перш"),(2,"друг"),(3,"трет"),(4,"четверт"),(5,"п'ят"),(6,"шост"),(7,"сьом"),(8,"восьм"),(9,"дев'ят"),(10,"десят")]:
    for ending,suffix in {"ий":"й","ій":"й","а":"а","я":"я","е":"е","є":"є","у":"у","ю":"ю","ого":"го","ому":"му","им":"м","ім":"м","ої":"ї","ій":"й","их":"х"}.items(): ORDINAL[root+ending]=(value,"-"+suffix)
DENOM = {}
for value,words in [(2,"половина половины половину половиной половини half halves hälfte halb halbe halben"),
    (3,"треть трети третьих третью третей третина третини третіх third thirds drittel"),
    (4,"четверть четверти четвертей четвертая четвертой четвертую четвертых чверть чверті quarter quarters viertel"),
    (5,"пятая пятой пятую пятых fifth fifths"),(6,"шестая шестой шестую шестых sixth sixths"),
    (7,"седьмая седьмой седьмую седьмых seventh sevenths"),(8,"восьмая восьмой восьмую восьмых eighth eighths"),
    (9,"девятая девятой девятую девятых ninth ninths"),(10,"десятая десятой десятую десятых десята десятої десятих tenth tenths"),
    (100,"сотая сотой сотую сотых сота сотої сотих hundredth hundredths"),(1000,"тысячная тысячной тысячных тисячна тисячної тисячних thousandth thousandths")]: add(value,words,DENOM)
GERMAN_UNITS={fold(k):CARDINAL[fold(k)] for k in "ein eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig".split()}


def german_value(word):
    if word in GERMAN_UNITS:return GERMAN_UNITS[word]
    for scale,value in [("tausend",1000),("hundert",100)]:
        if scale in word:
            left,right=word.split(scale,1)
            a=german_value(left) if left else 1
            b=german_value(right) if right else 0
            return a*value+b if a is not None and b is not None else None
    if "und" in word:
        left,right=word.split("und",1)
        if left in GERMAN_UNITS and right in GERMAN_UNITS and GERMAN_UNITS[left]<10 and GERMAN_UNITS[right]>=20:
            return GERMAN_UNITS[left]+GERMAN_UNITS[right]
    return None


def ordinal(word):
    if word in ORDINAL:return ORDINAL[word]
    if word.startswith("erst"):return (1,".") if word[4:] in ("","e","en","er","es","em") else None
    if word.startswith("zweit"):return (2,".") if word[5:] in ("","e","en","er","es","em") else None
    if word.startswith("dritt"):return (3,".") if word[5:] in ("","e","en","er","es","em") else None
    for ending in ("sten","ster","stes","stem","ste","ten","ter","tes","tem","te"):
        if word.endswith(ending):
            value=german_value(word[:-len(ending)])
            if value is not None:return value,"."
    return None


def detect_locale(text):
    if re.search("[ієїґІЇЄҐ]",text):return "uk"
    if re.search("[а-яА-ЯёЁ]",text):return "ru"
    if re.search(r"\b(?:und|der|die|das|einen|eine|ist|für|acht|zwei|drei|ein|halb|halbe|halben)\b|[äöüß]",text,re.I):return "de"
    return "en"


def written(value,locale):
    value=Fraction(value)
    if value.denominator==1:return str(value.numerator)
    if value.denominator in {2,4,5,10,20,25,50,100,1000}:
        result=format(float(value),".8f").rstrip("0").rstrip(".")
        return result.replace(".",",") if locale in {"ru","uk","de"} else result
    return str(value.numerator)+"/"+str(value.denominator)


def replacements(text,locale=None):
    locale=locale or detect_locale(text)
    matches=list(WORD.finditer(text));result=[];i=0
    while i<len(matches):
        start=i;word=fold(matches[i].group());j=i;group=0;total=0;last=None;seen=False;suffix=None
        # Explicit half-unit compounds retain their physical meaning.
        halves={"полминуты":"минуты","полчаса":"часа","полграмма":"грамма","полкилограмма":"килограмма","поллитра":"литра","полстакана":"стакана"}
        if word in halves:
            result.append((matches[i].start(),matches[i].end(),written(Fraction(1,2),locale)+" "+halves[word]));i+=1;continue
        if word in {"полтора","полторы","полутора","півтора","півтори"}:
            result.append((matches[i].start(),matches[i].end(),written(Fraction(3,2),locale)));i+=1;continue
        multiple={"вдвое":2,"втрое":3,"вчетверо":4,"впятеро":5,"удвічі":2,"вдвічі":2,"утричі":3,"втричі":3}
        if word in multiple:
            result.append((matches[i].start(),matches[i].end(),("у " if locale=="uk" else "в ")+str(multiple[word])+(" рази" if locale=="uk" else " раза")));i+=1;continue
        while j<len(matches):
            current=fold(matches[j].group())
            separator=text[matches[j-1].end():matches[j].start()] if j>start else ""
            if j>start and not (separator.isspace() or separator=="-"):break
            if current in {"and","und"} and seen and j+1<len(matches) and (group>=100 or total):
                j+=1;continue
            value=CARDINAL.get(current)
            scale=SCALE.get(current)
            if value is None and scale is None:value=german_value(current)
            # Articles are not numbers outside a numeric quantity or compound.
            if j==start and current in {"ein","eine","einen","einem","einer","eines"} and locale=="de":
                following=fold(matches[j+1].group()) if j+1<len(matches) else ""
                if following not in SCALE and following not in DENOM and not re.match(r"^(jahr|tag|woche|monat|stunde|minute|sekunde|liter|gramm|kilogramm|meter|kilometer|milligramm|euro|prozent|mal)",following):break
            if value is None and scale is None:
                break
            if scale:
                total+=(group or 1)*scale;group=0;last=None
            elif value==100 and group and group<10:
                group*=100;last=100
            else:
                if locale=="en" and 10<=group<20 and value>=10 and value<100:
                    group=group*100+value;last=value;seen=True;j+=1;continue
                if last is not None and ((last<20) or (20<=last<100 and not 0<value<10) or (last>=100 and value>=100)):
                    break
                group+=value;last=value
            seen=True;j+=1
        number=total+group
        if seen and j<len(matches) and fold(matches[j].group()) in {"point","komma","запятая","кома"}:
            k=j+1;digits=[]
            while k<len(matches) and text[matches[k-1].end():matches[k].start()].isspace():
                value=CARDINAL.get(fold(matches[k].group()))
                if value is None or value>9:break
                digits.append(str(value));k+=1
            if digits:number=Fraction(number)+Fraction(int("".join(digits)),10**len(digits));j=k
        if seen and j<len(matches) and fold(matches[j].group()) in {"and","и","und"}:
            k=j+1
            if k<len(matches) and fold(matches[k].group()) in {"a","an"}:k+=1
            if k<len(matches) and fold(matches[k].group()) in {"half","halfes","hälfte","половина","половиной"}:
                number=Fraction(number)+Fraction(1,2);j=k+1
        # Fractions are resolved before ordinals: one tenth, две трети.
        if seen and j<len(matches) and text[matches[j-1].end():matches[j].start()].isspace():
            denominator=DENOM.get(fold(matches[j].group()))
            if denominator:
                number=Fraction(number,denominator);j+=1
            else:
                ending=ordinal(fold(matches[j].group()))
                if ending and number>=20 and ending[0]<10:
                    number+=ending[0];suffix=ending[1];j+=1
        if not seen:
            value=ordinal(word)
            if value:
                number,suffix=value;seen=True;j=start+1
            elif word in {"half","половина","половину","треть","четверть","чверть"}:
                number=Fraction(1,DENOM[word]);seen=True;j=start+1
                if word=="half" and j<len(matches) and fold(matches[j].group()) in {"a","an"} and text[matches[j-1].end():matches[j].start()].isspace():j+=1
        if seen:
            end=matches[j-1].end()
            result.append((matches[start].start(),end,str(int(number))+suffix if suffix else written(number,locale)))
            i=j
        else:i+=1
    return result


def to_digits(text,locale=None):
    changes=replacements(text,locale)
    for start,end,value in reversed(changes):text=text[:start]+value+text[end:]
    return text


def word_spans(text):
    """Normalized number tokens with spans in the original string, for ASR timing."""
    changes=replacements(text);segments=[];cursor=0
    for start,end,value in changes:
        if start>cursor:segments.append((text[cursor:start],cursor,None))
        segments.append((value,start,end));cursor=end
    segments.append((text[cursor:],cursor,None))
    result=[]
    for value,start,end in segments:
        for token in TOKEN.finditer(fold(value)):
            normalized=token.group()
            if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?(?:/\d+)?",normalized):
                normalized=str(Fraction(normalized.replace(",",".")))
            result.append((normalized,start+token.start() if end is None else start,start+token.end() if end is None else end))
    return result


def comparison_tokens(text):
    return [token for token,_,_ in word_spans(str(text))]
