import array
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
import narration_ending as ending
import store


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for real audio verification')
class NarrationEndingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        data=patch.object(store,'DATA_ROOT',self.root/'data');data.start();self.addCleanup(data.stop)
        self.source=self.root/'original.wav'
        self.samples=array.array('h',(round(10000*math.sin(2*math.pi*330*i/48000)) for i in range(48000)))
        with wave.open(str(self.source),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(self.samples.tobytes())
        self.project={'id':'a'*24,'revision':1,'assets':[],'tracks':[]}
        self.imports=0
        def import_asset(project,source,role):
            self.imports+=1
            dest=self.root/f'import-{self.imports}.flac';shutil.copy2(source,dest)
            asset=store.asset_record(dest,self.project['id'],role)
            self.project['assets'].append(asset);return asset
        for target,name,value in [(store,'project_dir',lambda pid:self.root),
                                  (store,'load_project',lambda pid:self.project),
                                  (store,'save_project',lambda project:None),
                                  (store,'import_asset_file',import_asset)]:
            p=patch.object(target,name,side_effect=value);p.start();self.addCleanup(p.stop)

    def test_audio_is_unchanged_then_exactly_one_and_a_half_seconds_of_silence(self):
        before=self.source.read_bytes()
        path,receipt=ending.prepare_file(self.project['id'],self.source)
        decoded=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','s16le','-acodec','pcm_s16le','-'])
        samples=array.array('h');samples.frombytes(decoded)
        self.assertEqual(samples[:48000],self.samples)
        self.assertEqual(len(samples),120000)
        self.assertEqual(max(abs(x) for x in samples[48000:]),0)
        self.assertAlmostEqual(receipt['duration'],2.5,places=3)
        self.assertEqual(self.source.read_bytes(),before)

    def test_reanalysis_reuses_prepared_asset_without_another_pause_or_import(self):
        first=ending.import_audio(self.project,self.source)
        self.assertTrue(ending.prepared(first))
        self.assertEqual(ending.prepare_asset(self.project,first)['id'],first['id'])
        self.assertEqual(ending.import_audio(self.project,self.source)['id'],first['id'])
        self.assertEqual(ending.import_audio(self.project,first['path'])['id'],first['id'])
        self.assertEqual(self.imports,1)
        self.assertAlmostEqual(store.media_duration(Path(first['path'])),2.5,places=3)

    def test_local_effects_are_reversible_and_keep_one_closing_pause(self):
        dry=ending.import_audio(self.project,self.source)
        reverb={'enabled':True,'preset':'office','amount':70}
        noise={'enabled':True,'amount':60}
        wet=ending.import_audio(self.project,self.source,reverb=reverb,room_noise=noise)
        self.assertNotEqual(dry['id'],wet['id'])
        self.assertTrue(ending.prepared(wet))
        self.assertAlmostEqual(store.media_duration(Path(wet['path'])),2.5,places=3)
        decoded=subprocess.check_output(['ffmpeg','-v','error','-i',wet['path'],'-ac','1','-f','f32le','-'])
        samples=array.array('f');samples.frombytes(decoded)
        self.assertGreater(max(abs(x) for x in samples[48000:57600]),.0001)
        self.assertLess(max(abs(x) for x in samples[-4800:]),.0001)
        self.assertEqual(ending.import_audio(self.project,self.source,reverb=reverb,room_noise=noise)['id'],wet['id'])
        self.assertEqual(ending.import_audio(self.project,self.source)['id'],dry['id'])
        self.assertEqual(self.imports,2)

    def test_cached_file_does_not_reencode_and_modified_output_is_rebuilt(self):
        path,_=ending.prepare_file(self.project['id'],self.source)
        with patch.object(ending.subprocess,'run',wraps=subprocess.run) as run:
            self.assertEqual(ending.prepare_file(self.project['id'],self.source)[0],path)
            run.assert_not_called()
        path.write_bytes(b'damaged')
        path,receipt=ending.prepare_file(self.project['id'],self.source)
        self.assertAlmostEqual(receipt['duration'],2.5,places=3)
        self.assertTrue(path.stat().st_size>100)

    def test_tempo_change_keeps_pause_at_one_and_a_half_seconds(self):
        raw=self.root/'paced.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(self.source),'-af','atempo=1.1',str(raw)],check=True)
        path,receipt=ending.prepare_file(self.project['id'],raw)
        self.assertAlmostEqual(receipt['duration']-store.media_duration(raw),1.5,places=3)
        self.assertLess(receipt['speech_duration'],1.)

    def test_last_picture_covers_the_pause_in_the_plan_and_real_export(self):
        import planner
        from PIL import Image
        voice,receipt=ending.prepare_file(self.project['id'],self.source)
        plan=planner.build_plan('One complete sentence.', {'weights':{'stock_photo':100}}, 'Test',
            receipt['duration'], alignment=[{'text':'One complete sentence.','start':0.,'end':1.}])
        self.assertEqual(plan['frames'][-1]['end'],2.5)
        image=self.root/'picture.png';Image.new('RGB',(160,90),(40,180,90)).save(image)
        manifest=self.root/'project.json';manifest.write_text(json.dumps({
            'width':160,'height':90,'fps':25,'layer_mode':'item','timeline_layers':[
                {'clips':[{'type':'image','source':str(image),'start':f['start'],
                    'duration':f['end']-f['start'],'x':.5,'y':.5,'width':1.,'height':1.} for f in plan['frames']]},
                {'clips':[{'type':'audio','source':str(voice),'start':0,'duration':receipt['duration']}]}]}))
        renderer=Path(__file__).resolve().parents[2]/'engine'/'render.py'
        output=self.root/'result.mp4'
        result=subprocess.run([sys.executable,str(renderer),'--project',str(manifest),'--output',str(output)],
            capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout[-1000:]+result.stderr[-1000:])
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-map','0:v',
            '-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
        frame_size=160*90*3
        self.assertEqual(len(raw)//frame_size,63)
        # Every frame after the spoken second, including the final output frame, retains the picture.
        for index in range(25,63):
            frame=raw[index*frame_size:(index+1)*frame_size]
            self.assertLess(sum(abs(value-(40,180,90)[i%3]) for i,value in enumerate(frame))/frame_size,4)


if __name__=='__main__':unittest.main()
