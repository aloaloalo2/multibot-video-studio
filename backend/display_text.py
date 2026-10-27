"""Assembly-only display formatting; source scripts are never modified."""
import copy

def clean(text):
    value=str(text).rstrip();suffix=''
    while value:
        if value[-1] in ',.!':value=value[:-1].rstrip()
        elif value[-1] in '\"\'»”’)]}':suffix=value[-1]+suffix;value=value[:-1].rstrip()
        else:break
    return value.rstrip()+suffix

def clean_words(words):
    if not isinstance(words,list):return words
    result=copy.deepcopy(words)
    while result:
        result[-1]['text']=clean(result[-1].get('text',''))
        if result[-1]['text']:break
        result.pop()
    return result
