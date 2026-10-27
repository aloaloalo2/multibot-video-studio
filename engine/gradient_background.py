"""Deterministic four-point gradient, shared math with the native canvas preview."""
import hashlib,json,math,subprocess
from pathlib import Path
import numpy as np

def frame(config,time,width=320,height=180):
    yy,xx=np.mgrid[0:height,0:width];xx=xx/max(1,width-1);yy=yy/max(1,height-1)
    total=np.zeros((height,width));rgb=np.zeros((height,width,3))
    phase=time*float(config.get('speed',.05))*2*math.pi;amp=float(config.get('amplitude',.14));soft=float(config.get('softness',.1))
    points=config.get('points',[[.15,.15],[.85,.15],[.8,.85],[.2,.85]])
    for i,(color,point) in enumerate(zip(config['colors'],points)):
        px=max(.02,min(.98,point[0]+amp*math.sin(phase+i*1.7)));py=max(.02,min(.98,point[1]+amp*math.cos(phase*.82+i*1.3)))
        weight=1/(((xx-px)**2+(yy-py)**2+soft)**1.8)
        value=np.array([int(color[j:j+2],16) for j in (1,3,5)])
        total+=weight;rgb+=weight[:,:,None]*value
    return np.clip(np.rint(rgb/total[:,:,None]),0,255).astype('uint8')

def video(config,duration,fps,work):
    key=hashlib.sha256(json.dumps([config,duration,fps],sort_keys=True).encode()).hexdigest()[:20]
    path=Path(work)/('gradient-'+key+'.mkv')
    if path.exists():return path
    command=['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','320x180','-framerate',str(fps),'-i','pipe:0','-an','-c:v','ffv1','-level','3','-pix_fmt','bgr0',str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for n in range(math.ceil(duration*fps)):process.stdin.write(frame(config,n/fps).tobytes())
        process.stdin.close();error=process.stderr.read();code=process.wait(timeout=30)
        if code:raise RuntimeError(error.decode(errors='replace')[:500])
    except BaseException:
        process.kill();process.wait();raise
    return path
