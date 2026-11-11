"""Studio-wide exact words and phrases excluded from new writer output."""
import re
import unicodedata

LEGACY_ENTRIES=['стоит','стоят','белок','білок','сахар','гвоздика','душа']
CYR=r'[а-яіїєґ]'
FAMILIES={
    'белок':CYR+r'*(?:белок|белк)'+CYR+'*',
    'белка':CYR+r'*(?:белок|белк)'+CYR+'*',
    'білок':CYR+r'*(?:білок|білк)'+CYR+'*',
    'сахар':CYR+'*сахар'+CYR+'*',
    'сахара':CYR+'*сахар'+CYR+'*',
    'гвоздика':CYR+'*гвозди[кч]'+CYR+'*',
    'душа':r'душ(?:а|и|е|у|ой|ою|ам|ами|ах)',
}


def folded(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().replace('ё','е').replace('’',"'").replace('\u0301','').split())


def normalize(value):
    if value is None:
        return []
    if isinstance(value,str):
        value=value.splitlines()
    if not isinstance(value,list) or len(value)>300:
        raise ValueError('Чорний список має містити не більше 300 слів або фраз')
    result,seen=[],set()
    for item in value:
        if not isinstance(item,str) or len(item)>160:
            raise ValueError('Кожен запис чорного списку має містити до 160 символів')
        item=' '.join(unicodedata.normalize('NFC',item).split())
        key=folded(item)
        if key and key not in seen:
            seen.add(key);result.append(item)
    if sum(map(len,result))>16000:
        raise ValueError('Чорний список завеликий. Скоротіть його до 16 000 символів')
    return result


def current():
    import store
    return normalize(store.global_settings().get('word_blacklist',[]))


def managed():
    import store
    settings=store.read_json(store.GLOBAL_SETTINGS_PATH,{})
    return isinstance(settings,dict) and 'word_blacklist' in settings


def without_legacy_bans(text):
    """The editable Studio list supersedes duplicated old global word-ban notes."""
    blocks=re.split(r'\n\s*\n',text)
    result=[]
    for block in blocks:
        lower=folded(block)
        banned=re.search(r'запрещ|заборон|блек\s*ліст',lower)
        legacy=re.search(r'\b(?:белок|белка|білок|сахар|сахара|гвоздика|стоит|стоят|душа|душе)\b',lower)
        if banned and legacy:
            continue
        result.append(block)
    return '\n\n'.join(result)


def matches(text,entries=None):
    text=folded(text)
    return [item for item in (current() if entries is None else normalize(entries))
            if re.search(r'(?<!\w)'+FAMILIES.get(folded(item),re.escape(folded(item)))+r'(?!\w)',text)]


def message(text,entries=None):
    found=matches(text,entries)
    return 'Чорний список студії: '+', '.join('«'+item+'»' for item in found[:12])+'. Перефразуйте ці місця зі збереженням змісту.' if found else ''
