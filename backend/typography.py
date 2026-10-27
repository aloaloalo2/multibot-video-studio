"""Reflow speech-bound words when a project changes its font."""
from PIL import ImageFont
from font_catalog import font_path
def reflow(project,clip,family):
 words=clip.get('text_words');clip['font_family']=family
 if not words:return
 width=float(project.get('width',1920))*float(clip.get('width',1));height=float(project.get('height',1080))*float(clip.get('height',1))
 left=min(w['x']-w['width']/2 for w in words);right=max(w['x']+w['width']/2 for w in words);center=(left+right)/2
 ys=sorted({round(w['y'],5) for w in words});middle=(ys[0]+ys[-1])/2;span=.78 if clip.get('text_role')=='full_frame' else .76 if center>.4 and center<.6 else .35
 size=int(clip.get('font_size',54))
 while True:
  font=ImageFont.truetype(str(font_path(family,clip.get('font_weight',400))),size)
  try:font.set_variation_by_axes([float(clip.get('font_weight',400)) if b'Weight' in a['name'] else a['default'] for a in font.get_variation_axes()])
  except (OSError,AttributeError):pass
  gap=font.getlength(' ');rows=[[]];lengths=[0]
  for word in words:
   length=font.getlength(word['text'])
   if rows[-1] and lengths[-1]+gap+length>width*span:rows.append([]);lengths.append(0)
   lengths[-1]+=length+(gap if rows[-1] else 0);rows[-1].append((word,length))
  if len(rows)*size*1.45<=height*.76 or size<=24:break
  size-=2
 top=middle*height-(len(rows)-1)*size*1.45/2;result=[]
 for index,row in enumerate(rows):
  x=center*width-lengths[index]/2
  for word,length in row:
   result.append({**word,'x':round((x+length/2)/width,6),'y':round((top+index*size*1.45)/height,6),'width':round((length+12)/width,6),'height':round(size*1.4/height,6)});x+=length+gap
 clip['text_words']=result;clip['font_size']=size
