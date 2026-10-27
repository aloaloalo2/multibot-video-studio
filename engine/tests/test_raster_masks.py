"""Avatar and panel masks retain smooth edges at their final export size."""
import sys,tempfile,unittest
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import raster_effects

class RasterMaskTest(unittest.TestCase):
    def test_circle_has_symmetric_fractional_edges_and_preserves_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';Image.new('RGB',(400,400),'white').save(source)
            path,width,height,pad=raster_effects.decorate(source,80,80,{'mask':'circle'},root)
            alpha=np.array(Image.open(path).getchannel('A'))
            self.assertEqual((width,height,pad),(80,80,0))
            self.assertEqual(int(alpha[0,0]),0);self.assertEqual(int(alpha[40,40]),255)
            self.assertGreater(np.count_nonzero((alpha>0)&(alpha<255)),100)
            np.testing.assert_array_equal(alpha,alpha[::-1,:])
            np.testing.assert_array_equal(alpha,alpha[:,::-1])
            self.assertAlmostEqual(float(alpha.sum()/255),np.pi*40**2,delta=80)

    def test_rounded_panel_keeps_smooth_edges(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';Image.new('RGB',(100,100),'white').save(source)
            path,width,height,pad=raster_effects.decorate(source,120,80,{'mask':'rounded','corner_radius':12,'stretch':True},root)
            alpha=np.array(Image.open(path).getchannel('A'))
            self.assertEqual((width,height,pad),(120,80,0))
            self.assertGreater(np.count_nonzero((alpha>0)&(alpha<255)),20)
            self.assertEqual(int(alpha[40,60]),255)

if __name__=='__main__':unittest.main()
