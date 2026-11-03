import tempfile,sys,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,language_thumbnails as thumbs

class LanguageThumbnailVersionsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=patch.object(store,'project_dir',return_value=self.root);p.start();self.addCleanup(p.stop)
        self.work=thumbs.folder('p','pl');self.work.mkdir(parents=True)
        Image.new('RGB',(64,36),'red').save(self.work/'thumbnail.png')
        Image.new('RGB',(64,36),'blue').save(self.work/'thumbnail-new.png')

    def test_new_result_keeps_legacy_v1_and_selects_v2_in_both_serving_paths(self):
        old=(self.work/'thumbnail.png').read_bytes();new=(self.work/'thumbnail-new.png').read_bytes()
        self.assertEqual([v['number'] for v in thumbs.versions('p','pl')],[1])
        made=thumbs.publish('p','pl',self.work/'thumbnail-new.png',{'job_started':12,'add_flag':True},'Add Poland flag')
        self.assertEqual(made['number'],2)
        self.assertEqual(thumbs.version_file('p','pl','v1.png').read_bytes(),old)
        self.assertEqual(thumbs.current_file('p','pl').read_bytes(),new)
        self.assertEqual((self.work/'thumbnail.png').read_bytes(),new)
        versions=thumbs.versions('p','pl')
        self.assertEqual([(v['number'],v['current']) for v in versions],[(2,True),(1,False)])
        self.assertEqual((self.work/'thumbnails/v2.prompt.txt').read_text(),'Add Poland flag')

    def test_recovery_is_idempotent_and_previous_version_can_be_read(self):
        one=thumbs.publish('p','pl',self.work/'thumbnail-new.png',{'job_started':12})
        again=thumbs.publish('p','pl',self.work/'thumbnail-new.png',{'job_started':12})
        self.assertEqual(one['name'],again['name'])
        self.assertEqual(len(thumbs.versions('p','pl')),2)
        thumbs.choose('p','pl','v1.png')
        self.assertEqual(thumbs.current_file('p','pl').name,'v1.png')

    def test_invalid_result_cannot_replace_current_image(self):
        before=(self.work/'thumbnail.png').read_bytes()
        bad=self.work/'bad.png';bad.write_bytes(b'incomplete')
        with self.assertRaises(OSError):thumbs.publish('p','pl',bad)
        self.assertEqual((self.work/'thumbnail.png').read_bytes(),before)
        self.assertEqual(len(thumbs.versions('p','pl')),1)
        with self.assertRaises(store.StudioError):thumbs.version_file('p','pl','../../voice.mp3')
