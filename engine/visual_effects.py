"""The same restrained color presets as the editor's CSS filters."""
import json
from pathlib import Path
PRESETS=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'visual-effects.json').read_text())
def filters(style):
 cfg=PRESETS.get(style,{});out=[]
 for key,default in [('brightness',1),('contrast',1)]:
  value=cfg.get(key,default)
  if value!=default:
   expr=f'clip(val*{value}\\,0\\,255)' if key=='brightness' else f'clip((val-127.5)*{value}+127.5\\,0\\,255)'
   out.append('lutrgb='+':'.join(channel+"='"+expr+"'" for channel in ['r','g','b']))
 s=cfg.get('saturate',1)
 if s!=1:
  weights=[.2126,.7152,.0722];out.append('colorchannelmixer='+':'.join(a+b+'='+str((1-s)*weights[j]+(s if i==j else 0)) for i,a in enumerate('rgb') for j,b in enumerate('rgb')))
 q=cfg.get('sepia',0)
 if q:
  matrix=[[.393,.769,.189],[.349,.686,.168],[.272,.534,.131]];out.append('colorchannelmixer='+':'.join(a+b+'='+str(matrix[i][j]*q+((1-q) if i==j else 0)) for i,a in enumerate('rgb') for j,b in enumerate('rgb')))
 return out
