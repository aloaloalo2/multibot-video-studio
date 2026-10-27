"""Raster graphics effects with the same geometry as the native preview."""
import hashlib,json,math
from pathlib import Path
from PIL import Image,ImageChops,ImageColor,ImageDraw,ImageFilter,ImageOps

def decorate(path,width,height,style,work):
    mask=style.get('mask','none');shadow=style.get('shadow')
    if mask=='none' and not shadow and not style.get('blur'):return Path(path),width,height,0
    key=hashlib.sha256((str(path)+str(Path(path).stat().st_mtime_ns)+str(width)+str(height)+json.dumps(style,sort_keys=True,default=str)).encode()).hexdigest()[:20]
    target=Path(work)/('graphic-'+key+'.png')
    pad=math.ceil(float(shadow['blur'])*3+max(abs(float(shadow['x'])),abs(float(shadow['y'])))+2) if shadow else 0
    if target.exists():return target,width+2*pad,height+2*pad,pad
    source=Image.open(path).convert('RGBA')
    fitted=source.resize((width,height),Image.Resampling.LANCZOS) if style.get('stretch') else ImageOps.fit(source,(width,height),method=Image.Resampling.LANCZOS) if mask=='circle' else ImageOps.contain(source,(width,height),method=Image.Resampling.LANCZOS)
    content=Image.new('RGBA',(width,height));content.alpha_composite(fitted,((width-fitted.width)//2,(height-fitted.height)//2))
    if mask!='none':
        # CSS clips the circular edge with fractional coverage. A mask drawn
        # directly at 80x80 had binary, visibly jagged steps in exported badges.
        # Supersample small masks while bounding memory for large canvases.
        sampling=max(1,min(4,4096//max(width,height)))
        alpha=Image.new('L',(width*sampling,height*sampling));draw=ImageDraw.Draw(alpha)
        bounds=(0,0,alpha.width-1,alpha.height-1)
        if mask=='circle':draw.ellipse(bounds,fill=255)
        else:draw.rounded_rectangle(bounds,radius=float(style.get('corner_radius',8))*sampling,fill=255)
        if sampling>1:alpha=alpha.resize((width,height),Image.Resampling.LANCZOS)
        content.putalpha(ImageChops.multiply(content.getchannel('A'),alpha))
    out=Image.new('RGBA',(width+2*pad,height+2*pad))
    if shadow:
        alpha=Image.new('L',out.size);alpha.paste(content.getchannel('A'),(pad+round(shadow['x']),pad+round(shadow['y'])));alpha=alpha.filter(ImageFilter.GaussianBlur(shadow['blur'])).point(lambda x:round(x*shadow['opacity']))
        layer=Image.new('RGBA',out.size,ImageColor.getrgb(shadow['color'])+(0,));layer.putalpha(alpha);out.alpha_composite(layer)
    out.alpha_composite(content,(pad,pad))
    if style.get('blur'):out=out.filter(ImageFilter.GaussianBlur(float(style['blur'])))
    out.save(target)
    return target,out.width,out.height,pad
