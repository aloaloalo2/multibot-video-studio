"""Pixel and export checks for native gradients, typography and transitions."""
import importlib.util,json,os,subprocess,sys,tempfile,unittest
import time
from unittest.mock import patch
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import gradient_background
import transition_graphics
import render as native_render

class NativeEffects(unittest.TestCase):
 def test_export_rejects_video_that_ends_before_audio(self):
  good={'streams':[{'codec_type':'video','duration':'2.0','nb_frames':'50'},{'codec_type':'audio','duration':'2.0'}]}
  native_render.verify_output_streams(good,2,25)
  broken={'streams':[{'codec_type':'video','duration':'1.5','nb_frames':'38'},{'codec_type':'audio','duration':'2.0'}]}
  with self.assertRaisesRegex(RuntimeError,'video duration'):
   native_render.verify_output_streams(broken,2,25)
 def test_animated_png_is_not_cached_as_a_still(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'animated.png';a=Image.new('RGB',(16,16),'red');b=Image.new('RGB',(16,16),'blue');a.save(source,save_all=True,append_images=[b],duration=100,loop=0)
   native_render.is_static_image.cache_clear()
   self.assertFalse(native_render.is_static_image(source))
 def test_cloud_sources_are_requested_then_waited_for(self):
  source=Path('/tmp/studio-cloud-test.png');events=[]
  result=subprocess.CompletedProcess([],0,stdout='{"failures":[]}',stderr='')
  with patch.object(native_render.shutil,'which',return_value='/usr/bin/swift'),patch.object(native_render.subprocess,'run',return_value=result) as run,patch.object(native_render,'cloud_sources_still_offline',side_effect=[[source],[]]),patch.object(native_render.time,'sleep'),patch.object(native_render,'emit',side_effect=lambda stage,**fields:events.append((stage,fields))):
   native_render.prepare_cloud_sources([source])
  self.assertEqual(run.call_count,1)
  self.assertEqual(events[0][1],{'completed':0,'total':1})
  self.assertEqual(events[-1][1],{'completed':1,'total':1})
  with self.assertRaisesRegex(ValueError,'хмарі'):
   native_render.prepare_cloud_sources([source],validate_only=True)
 def test_static_image_validation_does_not_launch_ffprobe(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'image.png';Image.new('RGB',(320,180),'red').save(source)
   native_render.probe.cache_clear()
   with patch.object(native_render.subprocess,'run',side_effect=AssertionError('FFprobe should not be launched')):
    info=native_render.probe(source)
   self.assertEqual(info['streams'][0]['codec_type'],'video')
   self.assertEqual((info['streams'][0]['width'],info['streams'][0]['height']),(320,180))
 def test_fast_animated_alpha_matches_reference_on_every_frame(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'transparent.png';Image.new('RGBA',(160,90),(255,30,20,165)).save(source)
   clip=dict(type='image',source=str(source),start=0,duration=1.2,trim_start=0,x=.5,y=.5,width=1.,height=1.,easing='ease_in_out',
     keyframes=[dict(time=0,scale=.7,opacity=.1),dict(time=.6,scale=1.,opacity=.8),dict(time=1.2,scale=1.2,opacity=.3)])
   bg=dict(type='animation',content_type='shape',color='#1d4a82',start=0,duration=1.2,x=.5,y=.5,width=1.,height=1.)
   project=dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[bg]),dict(clips=[clip])])
   manifest=root/'alpha.json';manifest.write_text(json.dumps(project));frames=[]
   for fast in ('0','1'):
    out=root/(fast+'.mp4');env={**os.environ,'MULTIBOT_FAST_ALPHA':fast}
    result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(manifest),'--output',str(out)],env=env,capture_output=True,text=True,timeout=60)
    self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr[-2000:])
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-map','0:v','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
    frames.append(np.frombuffer(raw,dtype=np.uint8).astype(np.int16))
   self.assertEqual(len(frames[0]),320*180*3*30)
   diff=np.abs(frames[0]-frames[1]);self.assertLess(float(diff.mean()),1.0);self.assertLess(float(np.quantile(diff,.99)),10)
 def test_fast_motion_trails_match_reference_on_every_frame(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'moving.png';Image.new('RGBA',(80,80),(250,100,35,190)).save(source)
   clip=dict(type='image',source=str(source),start=0,duration=1.2,trim_start=0,x=.1,y=.5,width=.25,height=.45,motion_blur=1,easing='ease_in_out',
     keyframes=[dict(time=0,x=.1,y=.5,opacity=.3),dict(time=.6,x=.6,y=.5,opacity=1.),dict(time=1.2,x=.9,y=.5,opacity=.6)])
   bg=dict(type='animation',content_type='shape',color='#263a55',start=0,duration=1.2,x=.5,y=.5,width=1.,height=1.)
   project=dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[bg]),dict(clips=[clip])])
   manifest=root/'motion-alpha.json';manifest.write_text(json.dumps(project));frames=[]
   for fast in ('0','1'):
    out=root/(fast+'.mp4');env={**os.environ,'MULTIBOT_FAST_ALPHA':fast}
    result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(manifest),'--output',str(out)],env=env,capture_output=True,text=True,timeout=60)
    self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr[-2000:])
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-map','0:v','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
    frames.append(np.frombuffer(raw,dtype=np.uint8).astype(np.int16))
   self.assertEqual(len(frames[0]),320*180*3*30)
   diff=np.abs(frames[0]-frames[1]);self.assertLess(float(diff.mean()),1.0);self.assertLess(float(np.quantile(diff,.99)),10)
 def test_cached_still_matches_redecoded_still_on_every_frame(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'still.png';Image.new('RGBA',(160,90),(220,80,30,180)).save(source)
   clip=dict(type='image',source=str(source),start=0,duration=1.2,x=.5,y=.5,width=1.,height=1.,easing='ease_in_out',
     keyframes=[dict(time=0,scale=.8,opacity=.2),dict(time=1.2,scale=1.2,opacity=1.)])
   project=dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[clip])])
   manifest=root/'still.json';manifest.write_text(json.dumps(project));frames=[]
   for cache in ('0','1'):
    out=root/(cache+'.mp4');env={**os.environ,'MULTIBOT_STILL_CACHE':cache}
    result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(manifest),'--output',str(out)],env=env,capture_output=True,text=True,timeout=60)
    self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr[-2000:])
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-map','0:v','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
    frames.append(np.frombuffer(raw,dtype=np.uint8).astype(np.int16))
   self.assertEqual(len(frames[0]),320*180*3*30)
   diff=np.abs(frames[0]-frames[1]);self.assertLess(float(diff.mean()),.3);self.assertLess(float(np.quantile(diff,.99)),5)
 def test_parallel_segments_keep_order_and_monotonic_progress(self):
  clips=[dict(type='animation',content_type='shape',color=color,start=start,duration=.5,x=.5,y=.5,width=1.,height=1.)
         for color,start in [('#ff0000',0),('#0000ff',.5)]]
  project=dict(width=320,height=180,fps=25,duration=1,timeline_layers=[dict(clips=[clip]) for clip in clips])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);manifest=root/'parallel.json';manifest.write_text(json.dumps(project));out=root/'parallel.mp4';events=[]
   original=native_render.render_scene
   def delayed(scene,project_file,output,work,width,height,fps,index):
    if index==1:time.sleep(1)
    return original(scene,project_file,output,work,width,height,fps,index)
   with patch.object(native_render,'render_scene',side_effect=delayed),patch.object(native_render,'emit',side_effect=lambda stage,**fields:events.append((stage,fields))):
    native_render.render(manifest,out)
   finished=[data for stage,data in events if stage=='scene_done']
   self.assertEqual([item['scene'] for item in finished],[2,1])
   self.assertEqual([round(item['rendered_duration'],2) for item in finished],[.48,1.0])
   self.assertGreater(self.pixel(out,.2)[0],200)
   self.assertGreater(self.pixel(out,.8)[2],200)
 def test_motion_trails_are_bounded_by_actual_visible_motion(self):
  base=dict(position_units='pixels',x=0.,y=0.,keyframe_offset=0,easing='linear')
  slow={**base,'keyframes':[dict(time=0,x=0,y=0),dict(time=1,x=100,y=0)]}
  fast={**base,'keyframes':[dict(time=0,x=0,y=0),dict(time=1,x=600,y=0)]}
  mixed={**base,'keyframes':[dict(time=0,x=0,y=0),dict(time=.4,x=1000,y=0),dict(time=1,x=1020,y=0)]}
  self.assertEqual(native_render.visible_motion_trail_end(slow,1,25,1920,1080),0)
  self.assertEqual(native_render.visible_motion_trail_end(fast,1,25,1920,1080),1)
  self.assertGreater(native_render.visible_motion_trail_end(mixed,1,25,1920,1080),0)
  self.assertLess(native_render.visible_motion_trail_end(mixed,1,25,1920,1080),.5)
 def test_dynamic_scale_and_opacity_render_together(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'red.png';Image.new('RGB',(160,90),'#ff0000').save(source)
   clip=dict(type='image',source=str(source),start=0,duration=1,trim_start=0,x=.5,y=.5,width=1.,height=1.,
     keyframes=[dict(time=0,scale=.6,opacity=.2),dict(time=1,scale=1.2,opacity=1.)])
   out=self.render(dict(width=320,height=180,fps=25,duration=1,timeline_layers=[dict(clips=[clip])]),root,'scale-alpha')
   self.assertGreater(self.pixel(out,.88)[0],self.pixel(out,.12)[0]+40)
 def test_finished_transition_and_constant_opacity_do_not_add_per_pixel_filter(self):
  with tempfile.TemporaryDirectory() as tmp:
   clip=dict(type='animation',content_type='shape',color='#ff0000',start=0,end=2,duration=2,trim_start=0,x=.5,y=.5,width=1.,height=1.,opacity=1.,layer_order=0,clip_order=0,
     join_in=dict(type='crossfade',seam=.2,duration=.3),join_out=dict(type='crossfade',seam=1.5,duration=.3),
     keyframes=[dict(time=0,opacity=1.,scale=1.),dict(time=2,opacity=1.,scale=1.2)])
   scene=native_render.timeline_scene(.5,1.5,[clip],Path(tmp),320,180,'#101114');layer=scene['layers'][0]
   self.assertNotIn('join_in',layer);self.assertNotIn('join_out',layer)
   self.assertFalse(any('opacity' in point for point in layer['keyframes']))
   scene=native_render.timeline_scene(.2,.4,[clip],Path(tmp),320,180,'#101114')
   self.assertIn('join_in',scene['layers'][0])
 def test_all_eight_library_effects_export_and_monochrome_changes_pixels(self):
  from visual_effects import PRESETS
  self.assertEqual(len(PRESETS),8)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'color.png';Image.new('RGBA',(160,90),'#cf5020').save(source)
   for style in PRESETS:
    with self.subTest(style=style):
     clip=dict(type='image',source=str(source),visual_effect=style,start=0,duration=.4,x=.5,y=.5,width=1.,height=1.)
     out=self.render(dict(width=320,height=180,fps=25,timeline_layers=[dict(clips=[clip])]),root,style)
     pixel=self.pixel(out,.2)
     if style=='monochrome':self.assertLess(max(pixel)-min(pixel),6)
     self.assertGreater(out.stat().st_size,1000)
 def test_adjacent_fractional_frames_never_leave_a_blank_frame(self):
  clips=[dict(type='animation',content_type='shape',color='#ff0000' if i%2==0 else '#0000ff',start=i/10,duration=.1,x=.5,y=.5,width=1.,height=1.) for i in range(10)]
  project=dict(width=320,height=180,fps=25,duration=1,timeline_layers=[dict(clips=[c]) for c in clips])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);visual,_,total=native_render.timeline_plan(project,root/'test.json',320,180,25)
   for a,b in zip(visual,visual[1:]):self.assertAlmostEqual(a['end'],b['start'])
   self.assertTrue(all(active for _,_,active in native_render.timeline_segments(visual,total,25)))
   out=self.render(project,root,'fractional-seams')
   pixels=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-vf','scale=1:1','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
   self.assertEqual(len(pixels)//3,25)
   self.assertTrue(all(max(pixels[i:i+3])>220 for i in range(0,len(pixels),3)))
 def test_twenty_graphic_presets_cover_the_cut_and_clear_at_edges(self):
  styles=[style for style,cfg in transition_graphics.PRESETS.items() if cfg.get('kind')!='cinematic']
  self.assertEqual(len(styles),20)
  for style in styles:
   with self.subTest(style=style):
    self.assertEqual(transition_graphics.frame(style,.5,160,90).getchannel('A').getextrema(),(255,255))
    self.assertEqual(transition_graphics.frame(style,0,160,90).getchannel('A').getextrema(),(0,0))
    self.assertEqual(transition_graphics.frame(style,1,160,90).getchannel('A').getextrema(),(0,0))
 def test_fifteen_cinematic_presets_have_distinct_translucent_motion_and_encode(self):
  styles=[style for style,cfg in transition_graphics.PRESETS.items() if cfg.get('kind')=='cinematic']
  self.assertEqual(len(styles),15)
  appearances=set()
  with tempfile.TemporaryDirectory() as tmp:
   for style in styles:
    with self.subTest(style=style):
     first=transition_graphics.frame(style,0,160,90)
     middle=transition_graphics.frame(style,.5,160,90)
     end=transition_graphics.frame(style,1,160,90)
     self.assertEqual(first.getchannel('A').getextrema(),(0,0))
     self.assertEqual(end.getchannel('A').getextrema(),(0,0))
     self.assertGreater(middle.getchannel('A').getextrema()[1],50)
     self.assertLess(middle.getchannel('A').getextrema()[1],255)
     self.assertNotEqual(transition_graphics.frame(style,.25,160,90).tobytes(),transition_graphics.frame(style,.75,160,90).tobytes())
     appearances.add(middle.tobytes())
     movie=transition_graphics.video(style,.4,25,160,90,tmp)
     self.assertGreater(movie.stat().st_size,500)
  self.assertEqual(len(appearances),15)
 def test_cinematic_dissolves_blend_both_scenes_and_finish_cleanly(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for style in ('cin_amber_dissolve','cin_arctic_mist','cin_dusk'):
    with self.subTest(style=style):
     join=dict(type=style,duration=.4,seam=.6)
     clips=[dict(type='animation',content_type='shape',color='#ff0000',start=0,duration=1,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_out=join),dict(type='animation',content_type='shape',color='#0000ff',start=.6,duration=.6,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_in=join),dict(type='animation',content_type='graphic_transition',graphic_style=style,start=.6,duration=.4,trim_start=0,x=.5,y=.5,width=1.,height=1.)]
     out=self.render(dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[c]) for c in clips]),root,style)
     before=self.pixel(out,.4);middle=self.pixel(out,.8);after=self.pixel(out,1.16)
     self.assertGreater(before[0],220);self.assertGreater(after[2],220)
     self.assertGreater(middle[0],20);self.assertGreater(middle[2],20)
 def test_cinematic_transition_does_not_zoom_source_images(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'position.png';image=Image.new('RGB',(320,180),'black')
   from PIL import ImageDraw
   ImageDraw.Draw(image).rectangle((24,0,38,179),fill='white');image.save(source)
   for style in ('cin_amber_dissolve','cin_copper_sweep'):
    with self.subTest(style=style):
     join=dict(type=style,duration=.4,seam=.6)
     clips=[dict(type='image',source=str(source),start=0,duration=1.,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_out=join),dict(type='image',source=str(source),start=.6,duration=.6,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_in=join),dict(type='animation',content_type='graphic_transition',graphic_style=style,start=.6,duration=.4,trim_start=0,x=.5,y=.5,width=1.,height=1.)]
     out=self.render(dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[c]) for c in clips]),root,style+'-fixed')
     edges=[]
     for time in (.4,.8,1.16):
      raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(time),'-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
      row=raw[10*320*3:11*320*3];bright=[x for x in range(60) if sum(row[x*3:x*3+3])>330]
      self.assertTrue(bright);edges.append((min(bright),max(bright)))
     for edge in edges[1:]:self.assertLessEqual(max(abs(a-b) for a,b in zip(edges[0],edge)),1)
 def test_graphic_transition_keeps_alpha_in_native_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);join=dict(type='ribbon_tricolor',duration=.4,seam=.6)
   clips=[dict(type='animation',content_type='shape',color='#ff0000',start=0,duration=1.,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_out=join),dict(type='animation',content_type='shape',color='#0000ff',start=.6,duration=.6,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_in=join),dict(type='animation',content_type='graphic_transition',graphic_style='ribbon_tricolor',start=.6,duration=.4,trim_start=0,x=.5,y=.5,width=1.,height=1.)]
   out=self.render(dict(width=320,height=180,fps=25,duration=1.2,timeline_layers=[dict(clips=[c]) for c in clips]),root,'graphic')
   before=self.pixel(out,.4);middle=self.pixel(out,.8);after=self.pixel(out,1.1)
   self.assertGreater(before[0],220);self.assertGreater(after[2],220)
   self.assertLess(sum(abs(middle[i]-[197,77,67][i]) for i in range(3)),45)
 def render(self,project,root,name):
  path=root/(name+'.json');path.write_text(json.dumps(project));out=root/(name+'.mp4')
  result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(path),'--output',str(out)],capture_output=True,text=True,timeout=60)
  self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr[-2000:]);return out
 def pixel(self,path,time):
  raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(time),'-i',str(path),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
  return tuple(raw[:3])
 def test_transition_changes_pixels_and_keeps_real_boundary(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);join=dict(type='crossfade',duration=.4,seam=1)
   clips=[dict(id='red',type='animation',content_type='shape',color='#ff0000',start=0,duration=1.4,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_out=join),dict(id='blue',type='animation',content_type='shape',color='#0000ff',start=1,duration=1,trim_start=0,x=.5,y=.5,width=1.,height=1.,join_in=join)]
   out=self.render(dict(width=320,height=180,fps=25,duration=2,timeline_layers=[dict(clips=[c]) for c in clips]),root,'join')
   before=self.pixel(out,.8);middle=self.pixel(out,1.2);after=self.pixel(out,1.7)
   self.assertGreater(before[0],220);self.assertGreater(after[2],220)
   self.assertGreater(middle[0],40);self.assertGreater(middle[2],40)
 def test_gradient_moves_and_letter_blur_exports(self):
  config=dict(colors=['#213632','#72553f','#2d335d','#702d3d'],points=[[.1,.1],[.9,.1],[.8,.9],[.2,.9]],speed=.15,amplitude=.2,softness=.1)
  self.assertGreater(abs(gradient_background.frame(config,0).astype('int16')-gradient_background.frame(config,1).astype('int16')).mean(),3)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);text=dict(type='text',text='Рух',font_family='Golos',font_size=32,font_weight=500,color='#ffffff',start=0,duration=1.5,trim_start=0,x=.5,y=.5,width=1.,height=1.,word_entrance=dict(type='letters_blur',duration=.2,distance=12),text_words=[dict(text='Рух',start=.2,end=.55,x=.5,y=.5,width=.4,height=.3)])
   bg=dict(type='animation',content_type='gradient',gradient=config,start=0,duration=1.5,trim_start=0,x=.5,y=.5,width=1.,height=1.)
   out=self.render(dict(width=320,height=180,fps=25,duration=1.5,timeline_layers=[dict(clips=[bg]),dict(clips=[text])]),root,'letters')
   self.assertGreater(out.stat().st_size,1000)
 def test_fast_object_motion_trails_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);asset=root/'square.png';Image.new('RGBA',(40,40),'#ffffff').save(asset)
   clip=dict(type='image',source=str(asset),start=0,duration=.6,trim_start=0,x=.1,y=.5,width=.125,height=.222,motion_blur=1,easing='linear',keyframes=[dict(time=0,x=.1,y=.5),dict(time=.6,x=.9,y=.5)])
   out=self.render(dict(width=320,height=180,fps=25,duration=.6,timeline_layers=[dict(clips=[clip])]),root,'motion')
   self.assertGreater(out.stat().st_size,1000)

if __name__=='__main__':unittest.main()
