#!/usr/bin/env python3
"""Prepare an isolated GPU prototype from a saved Studio render snapshot."""
import hashlib, json, math, os, sys, time, subprocess
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
APP=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(APP/'engine'))
import render
from render_cache import RenderCache,key_for,renderer_version,scene_key
cache=RenderCache(max_bytes=None if os.environ.get('STUDIO_GPU_PERSISTENT_CACHE')=='1' else 0)
cache_version=renderer_version(APP/'engine') if cache.enabled else 'disabled'

if cache.enabled:
    original_text_bitmap=render.text_bitmap
    def cached_text_bitmap(layer,path,frame_width,frame_height):
        fields=('text','font_family','font_weight','font_size','size','width','height','line_height','text_align','color','raster_blur')
        font=render.first_font(layer.get('font_family','Arial'),layer.get('font_weight',400))
        key=key_for([cache_version,'text',{k:layer[k] for k in fields if k in layer},frame_width,frame_height,cache.source(font)])
        hit=cache.restore('media',key,path)
        if hit is not None:return hit['width'],hit['height']
        width,height=original_text_bitmap(layer,path,frame_width,frame_height)
        cache.publish('media',key,path,{'width':width,'height':height})
        return width,height
    render.text_bitmap=cached_text_bitmap
    original_decorate=render.raster_graphics.decorate
    def cached_decorate(path,width,height,style,work):
        fields=('mask','corner_radius','shadow','stretch','blur')
        raster_style={k:style[k] for k in fields if k in style}
        key=key_for([cache_version,'raster',cache.source(path),width,height,raster_style])
        target=Path(work)/('cached-raster-'+key+'.png')
        if target.exists():
            with render.Image.open(target) as image:w,h=image.size
            shadow=style.get('shadow');pad=math.ceil(float(shadow['blur'])*3+max(abs(float(shadow['x'])),abs(float(shadow['y'])))+2) if shadow else 0
            return target,w,h,pad
        hit=cache.restore('media',key,target)
        if hit is not None:return target,hit['width'],hit['height'],hit['pad']
        result=original_decorate(path,width,height,raster_style,work)
        cache.publish('media',key,result[0],{'width':result[1],'height':result[2],'pad':result[3]})
        return result
    render.raster_graphics.decorate=cached_decorate

def direct_movie(path, width, height, fps, frames):
    """Prepare generated graphics once in an AVFoundation-readable format."""
    if path.exists():return path
    cache_key=key_for([cache_version,'movie',path.name,width,height,fps])
    if cache.restore('media',cache_key,path) is not None:return path
    command=[render.FFMPEG,'-v','error','-nostdin','-y','-f','rawvideo','-pixel_format','rgba',
             '-video_size',f'{width}x{height}','-framerate',str(fps),'-i','pipe:0',
             '-an','-c:v','prores_ks','-profile:v','4444','-pix_fmt','yuva444p10le',str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for frame in frames:process.stdin.write(frame.tobytes())
        process.stdin.close();error=process.stderr.read();code=process.wait(timeout=60)
        if code:raise RuntimeError(error.decode(errors='replace')[:500])
    except BaseException:
        if process.poll() is None:process.kill()
        process.wait();path.unlink(missing_ok=True);raise
    finally:
        if process.stdin and not process.stdin.closed:process.stdin.close()
        if process.stderr:process.stderr.close()
    cache.publish('media',cache_key,path)
    return path

def direct_transition(style,duration,fps,width,height,work):
    module=render.transition_graphics
    key=hashlib.sha256(json.dumps([style,module.PRESETS[style],duration,fps,width,height]).encode()).hexdigest()[:20]
    return direct_movie(Path(work)/('transition-direct-'+key+'.mov'),width,height,fps,
        (module.frame(style,n/fps/duration,width,height) for n in range(math.ceil(duration*fps))))

def direct_gradient(config,duration,fps,work):
    from PIL import Image
    module=render.gradient_background
    key=hashlib.sha256(json.dumps([config,duration,fps],sort_keys=True).encode()).hexdigest()[:20]
    return direct_movie(Path(work)/('gradient-direct-'+key+'.mov'),320,180,fps,
        (Image.fromarray(module.frame(config,n/fps)).convert('RGBA') for n in range(math.ceil(duration*fps))))

if os.environ.get('STUDIO_GPU_DIRECT_GRAPHICS','1')!='0':
    render.transition_graphics.video=direct_transition
    render.gradient_background.video=direct_gradient

gradient_specs={}
if os.environ.get('STUDIO_GPU_PROCEDURAL_GRADIENT','0')=='1':
    def procedural_gradient(config,duration,fps,work):
        from PIL import Image
        key=hashlib.sha256(json.dumps([config,duration,fps],sort_keys=True).encode()).hexdigest()[:20]
        marker=(Path(work)/('gradient-procedural-'+key+'.png')).resolve()
        if not marker.exists():Image.new('RGB',(320,180)).save(marker)
        gradient_specs[str(marker)]=(config,duration,fps)
        return marker
    render.gradient_background.video=procedural_gradient

source=Path(sys.argv[1]); folder=Path(sys.argv[2]); cut=float(sys.argv[3]) if len(sys.argv)>3 else 60
folder.mkdir(parents=True,exist_ok=True); assets=folder/'assets';assets.mkdir(exist_ok=True)
m=json.loads(source.read_text()); fps=int(m['fps']);width=int(m['width']);height=int(m['height']);cut=math.ceil(cut*fps-1e-8)/fps
layers=[]
for layer in m['timeline_layers']:
    clips=[]
    for item in layer['clips']:
        start=float(item['start']);dur=float(item['duration'])
        if render.frame_index(start,fps)>=render.frame_index(cut,fps):continue
        c=dict(item);c['duration']=min(dur,cut-start)
        for key in ('join_in','join_out'):
            if key in c and float(c[key]['seam'])>=cut:c.pop(key)
        clips.append(c)
    if clips:layers.append({**layer,'clips':clips})
m['timeline_layers']=layers;m['duration']=cut
(folder/'cpu-project.json').write_text(json.dumps(m,ensure_ascii=False))
start_time=time.monotonic();visual,audio,total=render.timeline_plan(m,source,width,height,fps);slices=render.timeline_segments(visual,total,fps)
stream_chunks=os.environ.get('STUDIO_GPU_CHUNKS')=='1'
chunk_seconds=max(1,float(os.environ.get('STUDIO_GPU_CHUNK_SECONDS','30')))
chunk_folder=folder/'chunks'
pending_scenes=[];chunk_count=0
def atomic_json(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,default=str),encoding='utf-8')
    os.replace(temporary,path)
if stream_chunks:
    chunk_folder.mkdir(exist_ok=True)
    atomic_json(folder/'gpu-metadata.json',{'width':width,'height':height,'fps':fps,'duration':total,
                                           'scene_count':len(slices),'audio':audio})

def publish_chunk():
    global chunk_count
    if not stream_chunks or not pending_scenes:return
    # One preparer and one renderer run together. Bound completed work ahead
    # of the GPU so preparation cannot flood memory or the local disk queue.
    while True:
        try:consumed=int((chunk_folder/'consumed').read_text())
        except (OSError,ValueError):consumed=0
        if chunk_count-consumed<2:break
        time.sleep(.05)
    path=chunk_folder/f'{chunk_count:06d}.json'
    duration=pending_scenes[-1]['end']-pending_scenes[0]['start']
    atomic_json(path,{'width':width,'height':height,'fps':fps,'duration':duration,'scenes':pending_scenes})
    print(json.dumps({'stage':'chunk_ready','index':chunk_count,'path':str(path),
                      'start':pending_scenes[0]['start'],'end':pending_scenes[-1]['end']}),flush=True)
    chunk_count+=1;pending_scenes.clear()

def prepared_scene(scene):
    prepared.append(scene)
    if stream_chunks:
        pending_scenes.append(scene)
        if pending_scenes[-1]['end']-pending_scenes[0]['start']>=chunk_seconds-1e-8:publish_chunk()
transcodes={}
@lru_cache(maxsize=512)
def requires_timing_fallback(path):
    """Use the established path when packet timing cannot prove a fixed rate."""
    stream=next((s for s in render.probe(path).get('streams',[]) if s.get('codec_type')=='video'),{})
    try:
        # AVAssetReader exposes pixel buffers without FFmpeg's automatic track
        # orientation or non-square-pixel handling. Preserve those sources
        # through the established renderer until equivalent support exists.
        if stream.get('sample_aspect_ratio') not in (None,'1:1','0:1','N/A'):return True
        if stream.get('tags',{}).get('rotate') not in (None,'0','0.0'):return True
        if any(item.get('side_data_type')=='Display Matrix' for item in stream.get('side_data_list',[])):return True
        if stream.get('field_order') not in (None,'unknown','progressive'):return True
        if stream.get('color_transfer') in ('smpte2084','arib-std-b67'):return True
        pixel_format=stream.get('pix_fmt','')
        if not path.name.startswith('transition-direct-') and any(tag in pixel_format for tag in ('10','12','16','p010')):return True
        nominal=Fraction(stream['r_frame_rate']);average=Fraction(stream['avg_frame_rate'])
        if nominal<=0 or average<=0 or abs(float(nominal-average))>.01:return True
        result=subprocess.run([render.FFPROBE,'-v','error','-select_streams','v:0',
                               '-show_entries','packet=duration_time','-of','csv=p=0',str(path)],
                              capture_output=True,text=True,timeout=30)
        if result.returncode:return True
        durations=[float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        if not durations or min(durations)<=0:return True
        return max(durations)-min(durations)>max(.00002,min(durations)*.001)
    except (KeyError,ValueError,ZeroDivisionError,subprocess.TimeoutExpired):return True

def video_source(path):
    path=Path(path)
    if path.suffix.lower() not in ('.mkv','.webm'):return str(path)
    if str(path) in transcodes:return transcodes[str(path)]
    target=assets/('source-%03d.mov'%len(transcodes))
    result=subprocess.run([render.FFMPEG,'-v','error','-y','-i',str(path),'-an','-c:v','prores_ks','-profile:v','4444','-pix_fmt','yuva444p10le',str(target)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Could not convert temporary transition: '+result.stderr[-400:])
    transcodes[str(path)]=str(target);return str(target)

def ease(t,mode):
    t=max(0,min(1,t))
    return t**3 if mode=='ease_in' else 1-(1-t)**3 if mode=='ease_out' else t*t*(3-2*t) if mode=='ease_in_out' else t

def position(points,prop,default,maximum,t,normalized,easing):
    pp=[]
    for point in points:
        if prop in point:
            value=point[prop]
            if normalized and isinstance(value,float) and -1<=value<=1:value*=maximum
            pp.append({**point,prop:value})
    return render.scalar_value(pp,prop,default,t,easing)

def alpha_for(layer,points,elapsed,clip_len,easing,t,lag,speeds,frame):
    alpha=render.scalar_value(points,'opacity',float(layer.get('opacity',1)),t+elapsed,easing)
    if lag:alpha*=float(layer['trail_strength']) if speeds[frame]>=180 else 0
    for side in ('in','out'):
        join=layer.get('join_'+side)
        if not join:continue
        offset=float(layer.get('global_offset',0));seam=float(join['seam']);length=float(join['duration']);mode=join['type'];incoming=side=='in'
        if mode in render.transition_graphics.PRESETS:
            if render.transition_graphics.PRESETS[mode].get('kind')=='cinematic':
                p=ease((t+offset-seam)/length,'ease_in_out');alpha*=p if incoming else 1-p
            else:
                switch=seam+length*.5;alpha*=float(t+offset>=switch) if incoming else float(t+offset<switch)
        elif mode=='crossfade' or mode.startswith('zoom_'):
            p=ease((t+offset-seam)/length,'ease_in_out');alpha*=p if incoming else 1-p
    if layer.get('fade_in'):alpha*=ease((t+elapsed)/float(layer['fade_in']),easing)
    if layer.get('fade_out'):alpha*=ease((clip_len-t-elapsed)/float(layer['fade_out']),easing)
    return alpha

prepared=[]
for idx,(begin,end,active) in enumerate(slices,1):
    scene=render.timeline_scene(begin,end,active,assets,width,height,m.get('background','#101114'));duration=end-begin
    # Bake unsupported visual effects, blurred videos and animated images with
    # the established renderer. Regular transitions were separately checked.
    def needs_fallback(layer):
        kind=render.normalized_kind(layer)
        if layer.get('visual_effect') or (kind=='video' and layer.get('blur') and os.environ.get('STUDIO_GPU_VIDEO_BLUR','0')!='1'):return True
        if kind=='video' and str(Path(layer.get('source') or '.').resolve()) not in gradient_specs:
            video_path=render.resolve_source(render.source_value(layer),source,'video')
            if requires_timing_fallback(video_path):return True
        if kind=='image':
            image_path=render.resolve_source(render.source_value(layer),source,'animated image')
            if not render.is_static_image(image_path):return True
        return False
    fallback=os.environ.get('STUDIO_GPU_CPU_FALLBACK','1')!='0' and any(needs_fallback(layer) for layer in scene.get('layers',[]))
    if fallback:
        # CPU-baked slices still need a real source for procedural gradients.
        for layer in scene.get('layers',[]):
            spec=gradient_specs.get(str(Path(layer.get('source') or '.').resolve()))
            if spec:layer['source']=str(direct_gradient(*spec,assets))
        work=assets/f'fallback-work-{idx:03d}';work.mkdir(exist_ok=True)
        path=assets/f'fallback-{idx:03d}.mov'
        fallback_key=scene_key(scene,width,height,fps,render,cache,cache_version) if cache.enabled else None
        hit=cache.restore('media',fallback_key,path) if fallback_key else None
        original_options=render.video_encoder_options
        try:
            render.video_encoder_options=lambda hardware:['-c:v','prores_ks','-profile:v','3','-pix_fmt','yuv422p10le']
            if hit is None:
                render.render_scene(scene,source,path,work,width,height,fps,idx)
                if fallback_key:cache.publish('media',fallback_key,path)
        finally:render.video_encoder_options=original_options
        frames=[[0,0,1,1] for _ in range(round(duration*fps))]
        prepared_scene({'start':begin,'end':end,'color':scene['color'],'layers':[{'kind':'video','source':str(path),'width':width,'height':height,'trim_start':0,'first':0,'frames':frames}]})
        print('prepared scene',idx,'/',len(slices),f'timeline_end={end:.6f}',f'timeline_total={total:.6f}','CPU fallback',flush=True)
        continue
    records=[];expanded=[]
    for original in scene.get('layers',[]):
        if original.get('motion_blur') and render.normalized_kind(original)=='image':
            trail_end=render.visible_motion_trail_end(original,duration,fps,width,height)
            if trail_end:
                for fraction,weight in [(1,.1),(.5,.18)]:expanded.append({**original,'duration':min(float(original.get('duration',duration)),trail_end),'motion_lag':.5/fps*fraction,'trail_strength':weight*float(original['motion_blur'])})
        expanded.append(original)
    for li,original in enumerate(expanded):
        layer=dict(original);kind=render.normalized_kind(layer)
        if layer.get('visual_effect'):raise RuntimeError('Visual effect is not supported in the prototype')
        if kind=='text':
            path=assets/f'scene-{idx:03d}-text-{li:03d}.png';lw,lh=render.text_bitmap(layer,path,width,height)
            if layer.get('center'):layer={**layer,'x':(width-lw)/2,'y':(height-lh)/2}
            elif layer.get('position_units')=='normalized' or (isinstance(layer.get('x'),float) and isinstance(layer.get('y'),float) and 0<=layer['x']<=1 and 0<=layer['y']<=1):
                points=[]
                for point in layer.get('keyframes') or []:
                    point=dict(point)
                    if 'x' in point and (layer.get('position_units')=='normalized' or isinstance(point['x'],float) and -1<=point['x']<=1):point['x']=point['x']*width-lw/2
                    if 'y' in point and (layer.get('position_units')=='normalized' or isinstance(point['y'],float) and -1<=point['y']<=1):point['y']=point['y']*height-lh/2
                    points.append(point)
                layer={**layer,'x':layer['x']*width-lw/2,'y':layer['y']*height-lh/2,'keyframes':points,'position_units':'pixels'}
            input_kind='image'
        elif kind in ('image','video'):
            path=render.resolve_source(render.source_value(layer),source,f'scene {idx} layer {li}');lw=render.dimension(layer.get('width'),width,width//3);lh=render.dimension(layer.get('height'),height,height//3);input_kind=kind
        else:raise RuntimeError('Unsupported layer type '+kind)
        if input_kind=='image' and (layer.get('mask','none')!='none' or layer.get('shadow') or layer.get('blur')):
            path,lw,lh,pad=render.raster_graphics.decorate(path,lw,lh,layer,assets)
            if layer.get('position_units')=='pixels':x,y=float(layer.get('x',0)),float(layer.get('y',0));points=[dict(p) for p in layer.get('keyframes',[])]
            else:
                x,y=render.pixel(layer.get('x'),width,0),render.pixel(layer.get('y'),height,0)
                points=[{**p,**({'x':render.pixel(p['x'],width,0)} if 'x' in p else {}),**({'y':render.pixel(p['y'],height,0)} if 'y' in p else {})} for p in layer.get('keyframes',[])]
            layer={**layer,'x':x-pad,'y':y-pad,'position_units':'pixels','keyframes':[{**p,**({'x':p['x']-pad} if 'x' in p else {}),**({'y':p['y']-pad} if 'y' in p else {})} for p in points]}
        points=layer.get('keyframes') or [];elapsed=float(layer.get('keyframe_offset',0));clip_len=float(layer.get('clip_duration',duration));easing=layer.get('easing','linear');lag=float(layer.get('motion_lag',0));normalized=layer.get('position_units')!='pixels';x=render.pixel(layer.get('x'),width,0) if normalized else float(layer.get('x',0));y=render.pixel(layer.get('y'),height,0) if normalized else float(layer.get('y',0));speeds=render.sampled_motion_speeds(layer,duration,fps,width,height) if lag else []
        first=max(0,math.ceil(float(layer.get('start',0))*fps-1e-8));last=min(round(duration*fps),math.ceil((float(layer.get('start',0))+float(layer.get('duration',duration)))*fps-1e-8));frames=[]
        for frame in range(first,last):
            t=frame/fps;clock=max(0,t+elapsed-lag) if lag else t+elapsed
            px=position(points,'x',x,width,clock,normalized,easing);py=position(points,'y',y,height,clock,normalized,easing);scale=render.scalar_value(points,'scale',float(layer.get('scale',1)),clock,easing)
            if layer.get('scale_anchor')=='center':px+=lw*(1-scale)/2;py+=lh*(1-scale)/2
            for side in ('in','out'):
                join=layer.get('join_'+side)
                if not join:continue
                typ=join['type'];incoming=side=='in';q=ease((t+float(layer.get('global_offset',0))-float(join['seam']))/float(join['duration']),'ease_in_out')
                if typ.startswith('slide_'):
                    amount=1-q if incoming else q;sign=1 if (typ in ('slide_left','slide_up') and incoming) or (typ in ('slide_right','slide_down') and not incoming) else -1
                    if typ in ('slide_left','slide_right'):px+=sign*width*amount
                    else:py+=sign*height*amount
                if typ.startswith('zoom_'):
                    factor=(.88+.12*q if incoming else 1+.12*q) if typ=='zoom_in' else (1.12-.12*q if incoming else 1-.12*q)
                    px=width/2+(px-width/2)*factor;py=height/2+(py-height/2)*factor;scale*=factor
            if layer.get('slide_in'):px+=width*(1-ease((t+elapsed)/float(layer['slide_in']),easing))
            if layer.get('slide_out'):px-=width*(1-ease((clip_len-t-elapsed)/float(layer['slide_out']),easing))
            alpha=alpha_for(layer,points,elapsed,clip_len,easing,t,lag,speeds,frame)
            frames.append([round(px,4),round(py,4),round(scale,6),round(alpha,6)])
        path=Path(path)
        if input_kind=='image' and path.name.startswith('shape-'):
            # Core Image interpolates a 4x4 solid shape's edges while scaling,
            # spreading the edge over hundreds of pixels. Prepare it at its
            # target size so transition boundaries stay sharp.
            from PIL import Image
            shape_path=assets/f'{path.stem}-{lw}x{lh}.png'
            if not shape_path.exists():
                with Image.open(path) as source_image:
                    source_image.resize((lw,lh),Image.Resampling.NEAREST).save(shape_path)
            path=shape_path
        gradient=gradient_specs.get(str(path.resolve())) if input_kind=='video' else None
        path=Path(video_source(path)) if input_kind=='video' and not gradient else path
        if gradient:sw,sh=320,180
        else:
            info=render.probe(path);stream=next(s for s in info['streams'] if s.get('codec_type')=='video');sw=int(stream.get('width',lw));sh=int(stream.get('height',lh))
        factor=min(lw/sw,lh/sh) if not layer.get('stretch') else None
        dw=lw if factor is None else sw*factor;dh=lh if factor is None else sh*factor
        record={'kind':input_kind,'source':str(path),'width':dw,'height':dh,'trim_start':float(layer.get('trim_start',0)),'first':first,'frames':frames}
        if gradient:record['kind']='gradient';record['gradient']=gradient[0]
        elif input_kind=='video':
            # FFmpeg evaluates per-pixel opacity before rebasing the video
            # timestamps. Save extra values for an initial rounded seek offset.
            alphas=[frame[3] for frame in frames]
            alphas.extend(alpha_for(layer,points,elapsed,clip_len,easing,frame/fps,0,[],frame)
                          for frame in range(last,last+fps+1))
            record['alphaFrames']=alphas
        if input_kind=='video' and layer.get('blur'):record['blur']=float(layer['blur'])
        records.append(record)
    prepared_scene({'start':begin,'end':end,'color':scene['color'],'layers':records});print('prepared scene',idx,'/',len(slices),f'timeline_end={end:.6f}',f'timeline_total={total:.6f}',flush=True)
publish_chunk()
(folder/'gpu-project.json').write_text(json.dumps({'width':width,'height':height,'fps':fps,'duration':total,'scenes':prepared,'audio':audio},ensure_ascii=False,default=str))
print('prepared seconds',round(time.monotonic()-start_time,2),'scenes',len(prepared),flush=True)
print('cache media hits',cache.hits,'misses',cache.misses,flush=True)
