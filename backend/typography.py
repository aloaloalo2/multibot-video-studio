"""Reflow speech-bound words when a project changes its font."""
from PIL import ImageFont
from font_catalog import font_path
# a short word that leans on the next one never ends a line: prepositions, conjunctions, particles, articles
WEAK={*'а в во и й к ко о об обо с со у я на не ни но по за из от до для без под над при про что как это же ли бы то так уже ещё еще его её ее их который которая которое которые которых чтобы когда где если'.split(),
      *'і й та чи що як це ж би вже ще її з зі із від для без під над при про після через між який яка яке які котрий щоб коли де якщо'.split(),
      *'a an the of to in on at by for and or but with from as is it its that this which who when where if'.split(),
      *'der die das den dem des ein eine einen und oder mit von zu im am an auf für ist'.split()}

# the words of a number written out stay on one line
NUMBER=__import__('re').compile(r'^(\d[\d.,]*|од(ин|на|но|ного)|дв[ауе]\w*|тр[иёе]\w*|четыр\w*|чотир\w*|пят\w*|п.ят\w*|шест\w*|шіст\w*|сем\w*|сім\w*|восем\w*|вісім\w*|девят\w*|дев.ят\w*|десят\w*|сто|сот\w*|сорок\w*|тысяч\w*|тисяч\w*|миллион\w*|мільйон\w*|миллиард\w*|мільярд\w*|hundred|thousand|million|billion)$')


def breaks(texts,sizes,gap,limit):
    """Where the lines of a text break: as many lines as it needs, the lines of about one length, a line ending after
    a comma or a colon rather than in the middle of a phrase, and never on a word that leans on the next one (user,
    25 November 2026, Andromeda 40: «…звезда на / одной пластинке закрыла / спор…» — «дуже дивно чому текст так дивно
    розташований»). Returns the indices where a new line starts."""
    n=len(texts)
    if n<2:return []
    width=lambda a,b:sum(sizes[a:b])+gap*(b-a-1)
    lines,row=1,0.0   # the fewest lines it fits in, filled greedily
    for size in sizes:
        if row and row+gap+size>limit:lines+=1;row=size
        else:row+=size+(gap if row else 0)
    target=width(0,n)/lines
    def tail(i):   # what ending a line after word i-1 costs or saves
        word=texts[i-1].strip().lower()
        bare=word.strip('«»"“”„()')
        if word[-1:] in ',:;.!?—–' or word.endswith('»'):return -.15
        if bare in WEAK or len(bare)<=2:return .8
        if NUMBER.match(bare) and NUMBER.match(texts[i].strip().lower().strip('«»"“”„()')):return .8   # «сто / десять»
        return 0.0
    INF=float('inf');best=[[INF]*(n+1) for _ in range(lines+1)];back=[[0]*(n+1) for _ in range(lines+1)]
    best[0][0]=0.0
    for k in range(1,lines+1):
        for i in range(1,n+1):
            for j in range(k-1,i):
                if best[k-1][j]==INF:continue
                w=width(j,i)
                if w>limit and i-j>1:continue
                cost=best[k-1][j]+((w-target)/limit)**2+(tail(i) if i<n else 0.0)
                if cost<best[k][i]:best[k][i],back[k][i]=cost,j
    if best[lines][n]==INF:return [i for i in range(1,n)]
    cuts,i=[],n
    for k in range(lines,0,-1):
        i=back[k][i]
        if i:cuts.append(i)
    return sorted(cuts)


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
  gap=font.getlength(' ');sizes=[font.getlength(w['text']) for w in words]
  cuts=breaks([w['text'] for w in words],sizes,gap,width*span)
  rows=[list(zip(words[a:b],sizes[a:b])) for a,b in zip([0]+cuts,cuts+[len(words)])]
  lengths=[sum(sizes[a:b])+gap*(b-a-1) for a,b in zip([0]+cuts,cuts+[len(words)])]
  if len(rows)*size*1.45<=height*.76 or size<=24:break
  size-=2
 top=middle*height-(len(rows)-1)*size*1.45/2;result=[]
 for index,row in enumerate(rows):
  x=center*width-lengths[index]/2
  for word,length in row:
   result.append({**word,'x':round((x+length/2)/width,6),'y':round((top+index*size*1.45)/height,6),'width':round((length+12)/width,6),'height':round(size*1.4/height,6)});x+=length+gap
 clip['text_words']=result;clip['font_size']=size
