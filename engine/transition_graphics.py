"""Opaque graphic covers with a concealed cut, using editable preset definitions."""
import hashlib,json,math,subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np
PRESETS=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'graphic-transitions.json').read_text())
def clamp(v):return max(0,min(1,v))
def ease(v):v=clamp(v);return v*v*(3-2*v)

@lru_cache(maxsize=4)
def pixel_grid(width,height):
    return (np.arange(width,dtype=np.float32)[None,:]/width,
            np.arange(height,dtype=np.float32)[:,None]/height)

def cinematic_frame(config,p,width,height):
    if p<=0 or p>=1:return Image.new('RGBA',(width,height))
    xx,yy=pixel_grid(width,height)
    alpha=np.zeros((height,width),dtype=np.float32)
    premultiplied=np.zeros((height,width,3),dtype=np.float32)
    envelope=math.sin(math.pi*p)**2
    for lobe in config['lobes']:
        x=lobe['x']+lobe['dx']*(p-.5);y=lobe['y']+lobe['dy']*(p-.5)
        distance=np.sqrt(((xx-x)/lobe['rx'])**2+((yy-y)/lobe['ry'])**2)
        falloff=np.where(distance<.3,1-distance*(.4/.3),np.where(distance<.7,.6-(distance-.3)*(.47/.4),np.maximum(0,.13*(1-distance)/.3)))
        opacity=np.clip(falloff,0,1)*(lobe['opacity']*envelope)
        color=np.array([int(lobe['color'][i:i+2],16) for i in (1,3,5)],dtype=np.float32)
        premultiplied=premultiplied*(1-opacity[...,None])+opacity[...,None]*color
        alpha=opacity+alpha*(1-opacity)
    rgb=np.divide(premultiplied,alpha[...,None],out=np.zeros_like(premultiplied),where=alpha[...,None]>1e-7)
    rgba=np.empty((height,width,4),dtype=np.uint8)
    rgba[:,:,:3]=np.clip(np.rint(rgb),0,255).astype(np.uint8)
    rgba[:,:,3]=np.clip(np.rint(alpha*255),0,255).astype(np.uint8)
    return Image.fromarray(rgba)

def shapes(style,p,w,h):
    config=PRESETS[style];colors=config['colors'];kind=config['kind'];enter=p<=.5
    phase=clamp(p/.42 if enter else (1-p)/.42);result=[]
    if .42<=p<=.58:result.append(dict(kind='rect',x=0,y=0,w=w,h=h,color=colors[-1]))
    def progress(delay):return ease((phase-delay)/(1-delay))
    def rect(x,y,width,height,color):result.append(dict(kind='rect',x=x,y=y,w=width,h=height,color=color))
    if kind in {'sweep','bands'}:
        count=config.get('count',1);axis=config.get('axis','x');band=w/count if axis=='x' else h/count
        for i in range(count):
            reverse=bool(config.get('reverse')) ^ (bool(config.get('alternate')) and i%2==1)
            for k,color in enumerate(colors):
                q=progress(config.get('stagger',0)*i/max(1,count-1)+k*.07)
                if kind=='sweep':
                    extent=(w if axis=='x' else h)*q;offset=0 if enter!=reverse else (w if axis=='x' else h)-extent
                    rect(offset,0,extent,h,color) if axis=='x' else rect(0,offset,w,extent,color)
                elif axis=='x':
                    extent=h*q;offset=0 if enter!=reverse else h-extent;rect(i*band,offset,band+1,extent,color)
                else:
                    extent=w*q;offset=0 if enter!=reverse else w-extent;rect(offset,i*band,extent,band+1,color)
    elif kind=='gate':
        for k,color in enumerate(colors):
            q=progress(k*.1);axis=config['axis'];reverse=config.get('reverse',False)
            if axis=='x':
                if enter!=reverse:rect(w*(1-q)/2,0,w*q,h,color)
                else:rect(0,0,w*q/2,h,color);rect(w*(1-q/2),0,w*q/2,h,color)
            elif enter!=reverse:rect(0,h*(1-q)/2,w,h*q,color)
            else:rect(0,0,w,h*q/2,color);rect(0,h*(1-q/2),w,h*q/2,color)
    elif kind in {'tiles','dots'}:
        cols,rows=config['cols'],config['rows'];cw,ch=w/cols,h/rows
        for row in range(rows):
            for col in range(cols):
                order=((row+col)%2)*.6+(col/cols+row/rows)*.2 if config.get('checker') else (row*cols+col)/(rows*cols)
                q=progress(config.get('stagger',.3)*order);color=colors[(row+col)%len(colors)]
                if kind=='dots':result.append(dict(kind='circle',x=(col+.5)*cw,y=(row+.5)*ch,r=math.hypot(cw,ch)/2*q+.01,color=color))
                else:rect((col+.5)*cw-cw*q/2,(row+.5)*ch-ch*q/2,cw*q+1 if q else 0,ch*q+1 if q else 0,color)
    elif kind in {'paper','wave'}:
        for k,color in enumerate(colors):
            q=progress(k*.09);points=[]
            for i in range(65):
                y=i/64*h;wave=(math.sin(i*1.9)+math.sin(i*.73)*.45) if kind=='paper' else math.sin(i/64*math.pi*4+p*3)+.3*math.sin(i/64*math.pi*8-p*2)
                edge=(w*q+wave*w*.035*math.sin(q*math.pi)) if enter else (w*(1-q)+wave*w*.035*math.sin(q*math.pi));points.append([edge,y])
            result.append(dict(kind='polygon',points=([[0,0],[0,h]]+list(reversed(points))) if enter else ([[w,0]]+points+[[w,h]]),color=color))
    elif kind in {'rings','frames'}:
        for k,color in enumerate(colors):
            q=progress(k*.09)
            if kind=='rings':result.append(dict(kind='circle' if enter else 'ring',x=w*.5,y=h*.5,r=math.hypot(w,h)*.55*(q if enter else 1),inner=math.hypot(w,h)*.55*(1-q) if not enter else 0,color=color))
            elif enter:rect(w*(1-q)/2,h*(1-q)/2,w*q,h*q,color)
            else:
                x=w*q/2;y=h*q/2;rect(0,0,w,y,color);rect(0,h-y,w,y,color);rect(0,y,x,h-2*y,color);rect(w-x,y,x,h-2*y,color)
    elif kind=='cards':
        count=config.get('count',4)
        for i in range(count):
            for k,color in enumerate(colors):
                q=progress(config.get('stagger',.2)*i/max(1,count-1)+k*.06);band=h/count;extent=w*q;offset=0 if enter else w-extent;rect(offset,i*band,extent,band+1,color)
    return result if 0<p<1 else []

def frame(style,p,width,height):
    if PRESETS[style].get('kind')=='cinematic':return cinematic_frame(PRESETS[style],p,width,height)
    image=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(image)
    for item in shapes(style,p,width,height):
        color=item['color'];kind=item['kind']
        if kind=='rect' and item['w']>0 and item['h']>0:draw.rectangle((round(item['x']),round(item['y']),round(item['x']+item['w']),round(item['y']+item['h'])),fill=color)
        elif kind=='polygon':draw.polygon([tuple(p) for p in item['points']],fill=color)
        elif kind=='circle':draw.ellipse((item['x']-item['r'],item['y']-item['r'],item['x']+item['r'],item['y']+item['r']),fill=color)
        elif kind=='ring':
            mask=Image.new('L',image.size);md=ImageDraw.Draw(mask);md.ellipse((item['x']-item['r'],item['y']-item['r'],item['x']+item['r'],item['y']+item['r']),fill=255);inner=item['inner'];md.ellipse((item['x']-inner,item['y']-inner,item['x']+inner,item['y']+inner),fill=0);layer=Image.new('RGBA',image.size,color);layer.putalpha(mask);image.alpha_composite(layer);draw=ImageDraw.Draw(image)
    return image

def video(style,duration,fps,width,height,work):
    key=hashlib.sha256(json.dumps([style,PRESETS[style],duration,fps,width,height]).encode()).hexdigest()[:20];path=Path(work)/('transition-'+key+'.mkv')
    if path.exists():return path
    process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{width}x{height}','-framerate',str(fps),'-i','pipe:0','-an','-c:v','ffv1','-pix_fmt','bgra',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for n in range(math.ceil(duration*fps)):process.stdin.write(frame(style,n/fps/duration,width,height).tobytes())
        process.stdin.close();error=process.stderr.read();code=process.wait(timeout=30)
        if code:raise RuntimeError(error.decode(errors='replace')[:500])
    except BaseException:
        if process.poll() is None:process.kill()
        process.wait();path.unlink(missing_ok=True)
        raise
    finally:
        if process.stdin and not process.stdin.closed:
            try:process.stdin.close()
            except BrokenPipeError:pass
        if process.stderr:process.stderr.close()
    return path
