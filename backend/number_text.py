# -*- coding: utf-8 -*-
"""Deterministic post-ASR number formatting with original character spans."""
from __future__ import annotations
import re
import unicodedata
from fractions import Fraction

WORD = re.compile(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)*", re.UNICODE)
TOKEN = re.compile(r"(?:(?<!\w)[+-])?\d+(?:[.,]\d+)?(?:/\d+)?(?:-\d+(?:[.,]\d+)?)?(?:st|nd|rd|th|-(?:го|му|ми|й|я|е|ю|м|х|а|у))?|[^\W\d_]+", re.UNICODE)
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
    (20,"двадцать двадцати двадцатью twenty zwanzig двадцять двадцяти"),(30,"тридцать тридцати тридцатью thirty dreißig тридцять тридцяти"),
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
RU_ORDINAL = {}
UK_ORDINAL = {}
for value, word in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(),1):
    suffix = "th" if 10 <= value % 100 <= 20 else {1:"st",2:"nd",3:"rd"}.get(value%10,"th")
    ORDINAL[word] = (value,suffix)
for value, word in [(30,"thirtieth"),(40,"fortieth"),(50,"fiftieth"),(60,"sixtieth"),(70,"seventieth"),(80,"eightieth"),(90,"ninetieth"),(100,"hundredth"),(1000,"thousandth")]: ORDINAL[word]=(value,"th")
RU_ROOTS={"перв":1,"втор":2,"трет":3,"четверт":4,"пят":5,"шест":6,"седьм":7,"восьм":8,"девят":9,"десят":10,"одиннадцат":11,"двенадцат":12,"тринадцат":13,"четырнадцат":14,"пятнадцат":15,"шестнадцат":16,"семнадцат":17,"восемнадцат":18,"девятнадцат":19,"двадцат":20,"тридцат":30,"сороков":40,"пятидесят":50,"шестидесят":60,"семидесят":70,"восьмидесят":80,"девяност":90,"сот":100,"тысячн":1000}
ENDINGS={"ый":"й","ий":"й","ой":"й","ая":"я","ое":"е","ые":"е","ую":"ю","ого":"го","ому":"му","ым":"м","ом":"м","ых":"х","ыми":"ми","ей":"й","ья":"я","ье":"е","ью":"ю","ьего":"го","ьему":"му","ьим":"м","ьем":"м","ьих":"х","ьими":"ми"}
for root,value in RU_ROOTS.items():
    for ending,suffix in ENDINGS.items(): RU_ORDINAL[root+ending]=(value,"-"+suffix)
for value,root in [(1,"перш"),(2,"друг"),(3,"трет"),(4,"четверт"),(5,"п'ят"),(6,"шост"),(7,"сьом"),(8,"восьм"),(9,"дев'ят"),(10,"десят")]:
    for ending,suffix in {"ий":"й","ій":"й","а":"а","я":"я","е":"е","є":"є","у":"у","ю":"ю","ого":"го","ому":"му","им":"м","ім":"м","ої":"ї","ій":"й","их":"х"}.items(): UK_ORDINAL[root+ending]=(value,"-"+suffix)
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


def ordinal(word,locale=None):
    if locale == "ru":return RU_ORDINAL.get(word)
    if locale == "uk":return UK_ORDINAL.get(word)
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
    german=len(re.findall(r"\b(?:und|der|die|das|einen|eine|ist|für|acht|zwei|drei|ein|halb|halbe|halben)\b|[äöüß]",text,re.I))
    # English «people die» must not turn a whole English script German.
    english=len(re.findall(r"\b(?:the|and|you|is|of|that|it|with)\b",text,re.I))
    if german and german>=english:return "de"
    return "en"


def written(value,locale):
    value=Fraction(value)
    if value.denominator==1:return str(value.numerator)
    if value.denominator in {2,4,5,10,20,25,50,100,1000}:
        result=format(float(value),".8f").rstrip("0").rstrip(".")
        return result.replace(".",",") if locale in {"ru","uk","de"} else result
    return str(value.numerator)+"/"+str(value.denominator)


def english_pronoun_one(text,matches,i):
    previous=fold(matches[i-1].group()) if i and text[matches[i-1].end():matches[i].start()].isspace() else ""
    following=fold(matches[i+1].group()) if i+1<len(matches) and text[matches[i].end():matches[i+1].start()].isspace() else ""
    if previous in {"the","this","that","which","every","no","any","each","another","some","a","an","last","only","right","wrong","little","big","new","old"}:
        return True
    if following in {"who","whom","whose","that","which","of","another"}:
        return True
    # «a convincing one.»: an adjective after an article, then the sentence ends.
    if i>=2 and fold(matches[i-2].group()) in {"a","an","the"} and not following:
        return True
    # «the hardest one», «it was one.», «your body is offering one.»
    if len(previous)>3 and previous.endswith("est"):
        return True
    return text[matches[i].end():matches[i].end()+1] in {".","!","?"} and i>0


def english_ordinal(text,matches,i):
    previous=fold(matches[i-1].group()) if i and text[matches[i-1].end():matches[i].start()].isspace() else ""
    if previous in {"the","his","her","my","your","our","their","its"}:
        return True
    # «Second, keep your wake-up time steady.»: a list marker at the start of a sentence.
    return text[matches[i].end():matches[i].end()+1]=="," and not text[:matches[i].start()].strip(" \"'“‘(")[-1:].isalnum()


def replacements(text,locale=None):
    locale=locale or detect_locale(text)
    matches=list(WORD.finditer(text));result=[];i=0
    while i<len(matches):
        start=i;word=fold(matches[i].group());j=i;group=0;total=0;last=None;seen=False;suffix=None
        # Explicit half-unit compounds retain their physical meaning.
        halves={"полминуты":"минуты","полчаса":"часа","полгода":"года","полугода":"года","полграмма":"грамма","полкилограмма":"килограмма","поллитра":"литра","полстакана":"стакана"}
        if word in halves:
            result.append((matches[i].start(),matches[i].end(),written(Fraction(1,2),locale)+" "+halves[word]));i+=1;continue
        if locale == "ru" and word == "сотни" and i and fold(matches[i-1].group()) in {"до","около","почти"}:
            result.append((matches[i].start(),matches[i].end(),"100"));i+=1;continue
        if word in {"полтора","полторы","полутора","півтора","півтори"}:
            result.append((matches[i].start(),matches[i].end(),written(Fraction(3,2),locale)));i+=1;continue
        # English «one» is often a pronoun: «the one who», «a convincing one.», «one of them».
        if locale == "en" and word == "one" and english_pronoun_one(text,matches,i):
            i+=1;continue
        # A standalone English ordinal needs a determiner: «the first way», but «first aid»,
        # «need you first» and time units such as «every second» stay words.
        if locale == "en" and word in ORDINAL and not english_ordinal(text,matches,i):
            i+=1;continue
        # «300 million» already starts with digits; «a few thousand» is not an exact number.
        if word in SCALE and (re.search(r"\d\s+$",text[:matches[i].start()])
                              or (i and fold(matches[i-1].group()) in {"few","several","many","of"})):
            i+=1;continue
        # A bare plural scale is a vague amount: «shed millions of cells» is not 1000000.
        if word in {"millions","billions","millionen","milliarden"}:
            i+=1;continue
        # Indefinite expressions such as «одно из» and «одни из» stay in words.
        if (locale == "ru" and word in {"один", "одна", "одно", "одни"} and i+1<len(matches)
                and text[matches[i].end():matches[i+1].start()].isspace()
                and fold(matches[i+1].group()) == "из"):
            i+=1;continue
        # In the expression «одно с другим», «одно» is a pronoun, not a quantity.
        if (locale == "ru" and word == "одно" and i+2<len(matches)
                and text[matches[i].end():matches[i+1].start()].isspace()
                and text[matches[i+1].end():matches[i+2].start()].isspace()
                and fold(matches[i+1].group()) == "с"
                and fold(matches[i+2].group()) == "другим"):
            i+=1;continue
        multiple={"вдвое":2,"втрое":3,"вчетверо":4,"впятеро":5,"удвічі":2,"вдвічі":2,"утричі":3,"втричі":3}
        if word in multiple:
            result.append((matches[i].start(),matches[i].end(),("у " if locale=="uk" else "в ")+str(multiple[word])+(" рази" if locale=="uk" else " раза")));i+=1;continue
        while j<len(matches):
            current=fold(matches[j].group())
            separator=text[matches[j-1].end():matches[j].start()] if j>start else ""
            if j>start and not (separator.isspace() or separator=="-"):break
            if current in {"and","und"} and seen and j+1<len(matches) and (group>=100 or total):
                # «one hundred and five» is one number; «one hundred and keep» keeps its «and».
                following=fold(matches[j+1].group())
                if following in CARDINAL or following in SCALE or german_value(following) is not None:
                    j+=1;continue
                break
            value=CARDINAL.get(current)
            scale=SCALE.get(current)
            # Russian «семью» can mean a family rather than the number seven.
            # Only treat this ambiguous form as a number in an instrumental
            # phrase introduced by a matching preposition.
            if locale == "ru" and current == "семью":
                previous=fold(matches[j-1].group()) if j else ""
                if previous not in {"с","со","между","перед","над","за"}:
                    break
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
            elif locale == "ru" and k+1<len(matches):
                numerator=CARDINAL.get(fold(matches[k].group()))
                denominator=DENOM.get(fold(matches[k+1].group()))
                if (numerator is not None and denominator and 0<numerator<denominator
                        and text[matches[j].end():matches[k].start()].isspace()
                        and text[matches[k].end():matches[k+1].start()].isspace()):
                    number=Fraction(number)+Fraction(numerator,denominator);j=k+2
        # Fractions are resolved before ordinals: one tenth, две трети.
        if seen and j<len(matches) and text[matches[j-1].end():matches[j].start()].isspace():
            denominator=DENOM.get(fold(matches[j].group()))
            if denominator:
                number=Fraction(number,denominator);j+=1
            else:
                ending=ordinal(fold(matches[j].group()),locale)
                if ending and ((number>=20 and number%10==0 and ending[0]<10)
                               or (number>=100 and number%100==0 and ending[0]<100)):
                    number+=ending[0];suffix=ending[1];j+=1
        if not seen:
            value=ordinal(word,locale)
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


def word_spans(text,locale=None):
    """Normalized number tokens with spans in the original string, for ASR timing."""
    changes=replacements(text,locale);segments=[];cursor=0
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
    # Preserve numeric ranges as one token in both spoken and digit form.
    # Keep fractions and separate numbers distinct and retain source spans.
    joined=[]
    for item in result:
        value,start,end=item
        if (joined and re.fullmatch(r'\d+',joined[-1][0]) and re.fullmatch(r'\d+',value)
                and text[joined[-1][2]:start] in ('-', '–')):
            previous=joined.pop()
            joined.append((previous[0]+'-'+value,previous[1],end))
        else:
            joined.append(item)
    return joined


def comparison_tokens(text,locale=None):
    return [token for token,_,_ in word_spans(str(text),locale)]
