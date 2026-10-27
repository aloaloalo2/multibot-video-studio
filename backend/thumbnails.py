"""Small, source-preserving library previews cached by file identity."""
import hashlib,os,subprocess,threading,uuid
from pathlib import Path
from PIL import Image,ImageOps
LOCK=threading.Semaphore(2)
def get(path,kind,cache):
 path=Path(path);stat=path.stat();key=hashlib.sha256(f'{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:24]
 cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);dest=cache/(key+'.webp')
 if dest.exists():return dest
 with LOCK:
  if dest.exists():return dest
  temp=cache/(key+'-'+uuid.uuid4().hex+'.webp')
  try:
   if kind=='image':
    with Image.open(path) as source:
     source=ImageOps.exif_transpose(source);source.thumbnail((256,160),Image.Resampling.LANCZOS);image=Image.new('RGB',source.size,'#25252a');image.paste(source,mask=source.getchannel('A') if source.mode=='RGBA' else None);image.save(temp,format='WEBP',quality=78,method=3)
   elif kind=='video':
    result=subprocess.run(['ffmpeg','-v','error','-nostdin','-ss','.25','-i',str(path),'-frames:v','1','-vf','scale=256:160:force_original_aspect_ratio=decrease','-c:v','libwebp','-quality','75','-y',str(temp)],capture_output=True,timeout=20)
    if result.returncode or not temp.exists():raise ValueError('Thumbnail unavailable')
   else:raise ValueError('No visual preview')
   os.replace(temp,dest);return dest
  finally:
   if temp.exists():temp.unlink()
