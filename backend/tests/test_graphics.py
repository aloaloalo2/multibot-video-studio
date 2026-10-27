import importlib.util,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import graphics
spec=importlib.util.spec_from_file_location('raster_effects',Path(__file__).resolve().parents[2]/'engine'/'raster_effects.py');raster=importlib.util.module_from_spec(spec);spec.loader.exec_module(raster)

class GraphicTest(unittest.TestCase):
    def test_mask_shadow_preserve_source_and_make_real_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'portrait.png';Image.new('RGB',(100,100),'#d9a073').save(source);before=source.read_bytes()
            path,w,h,pad=raster.decorate(source,80,80,dict(mask='circle',shadow=dict(color='#000000',opacity=.2,blur=3,x=0,y=2)),root)
            image=Image.open(path)
            self.assertEqual(image.mode,'RGBA');self.assertEqual(source.read_bytes(),before)
            self.assertEqual(image.getpixel((pad+40,pad+40))[3],255)
            self.assertLess(image.getpixel((pad,pad))[3],20)
            self.assertGreater(w,80);self.assertEqual(w,h)
    def test_style_validation_rejects_malformed_effects(self):
        self.assertEqual(graphics.validate(dict(mask='circle',font_family='Golos'))['mask'],'circle')
        for style in [dict(mask='unknown'),dict(shadow={'color':'bad'}),dict(shadow={'blur':-1}),dict(font_family='../private')]:
            with self.assertRaises(ValueError):graphics.validate(style)

if __name__=='__main__':unittest.main()
