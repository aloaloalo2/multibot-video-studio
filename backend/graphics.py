"""Validated, portable graphics fields used by the editor and local renderer."""
import math
import re
import json
from pathlib import Path
from font_catalog import FONT_FAMILIES
VISUAL_EFFECTS=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'visual-effects.json').read_text())

FIELDS={'mask','corner_radius','shadow','font_family','font_weight','text_align','line_height','word_entrance','gradient','blur','motion_blur','visual_effect'}
def validate(source):
    result={}
    if 'visual_effect' in source:
        if source['visual_effect'] is not None and source['visual_effect'] not in VISUAL_EFFECTS:raise ValueError('Unknown visual effect')
        result['visual_effect']=source['visual_effect']
    def number(v,low,high):
        v=float(v)
        if not math.isfinite(v) or not low<=v<=high:raise ValueError('Invalid graphics value')
        return v
    if 'mask' in source:
        if source['mask'] not in {'none','circle','rounded'}:raise ValueError('Unknown mask')
        result['mask']=source['mask']
    if 'corner_radius' in source:result['corner_radius']=number(source['corner_radius'],0,200)
    if 'blur' in source:result['blur']=number(source['blur'],0,80)
    if 'motion_blur' in source:result['motion_blur']=number(source['motion_blur'],0,1)
    if 'font_family' in source:
        if source['font_family'] not in FONT_FAMILIES:raise ValueError('Unknown font')
        result['font_family']=source['font_family']
    if 'font_weight' in source:result['font_weight']=int(number(source['font_weight'],100,900))
    if 'text_align' in source:
        if source['text_align'] not in {'left','center','right'}:raise ValueError('Invalid text alignment')
        result['text_align']=source['text_align']
    if 'line_height' in source:result['line_height']=number(source['line_height'],.9,2)
    if 'word_entrance' in source:
        entrance=source['word_entrance']
        if entrance is None:result['word_entrance']=None
        else:
            if not isinstance(entrance,dict) or entrance.get('type') not in {'fade','up','down','left','right','pop','grow','shrink','blur','blur_up','letters_up','letters_fade','letters_blur'}:raise ValueError('Invalid word entrance')
            result['word_entrance']=dict(type=entrance['type'],duration=number(entrance.get('duration',.16),.05,.6),distance=number(entrance.get('distance',14),0,80))
    if 'gradient' in source:
        gradient=source['gradient']
        if not isinstance(gradient,dict):raise ValueError('Invalid gradient')
        colors=gradient.get('colors',[]);points=gradient.get('points',[[.15,.15],[.85,.15],[.8,.85],[.2,.85]])
        if len(colors)!=4 or any(not isinstance(c,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in colors):raise ValueError('A gradient requires exactly four colors')
        if not isinstance(points,list) or len(points)!=4 or any(not isinstance(p,list) or len(p)!=2 for p in points):raise ValueError('A gradient requires four points')
        result['gradient']=dict(colors=colors,points=[[number(p[0],0,1),number(p[1],0,1)] for p in points],speed=number(gradient.get('speed',.05),0,.5),amplitude=number(gradient.get('amplitude',.14),0,.4),softness=number(gradient.get('softness',.1),.02,.5))
    if 'shadow' in source:
        shadow=source['shadow']
        if shadow is None or shadow is False:result['shadow']=None
        elif isinstance(shadow,dict):
            color=str(shadow.get('color','#000000'))
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Invalid shadow color')
            result['shadow']=dict(color=color,opacity=number(shadow.get('opacity',.2),0,1),blur=number(shadow.get('blur',12),0,100),x=number(shadow.get('x',0),-200,200),y=number(shadow.get('y',4),-200,200))
        else:raise ValueError('Invalid shadow')
    return result
