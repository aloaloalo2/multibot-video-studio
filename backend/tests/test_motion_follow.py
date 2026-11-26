"""Motion code pinned to its frame's picture (motion_code.follow_of, info.pin in frontend/motion-code.js)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import motion_code


def project(code):
    clips = [dict(id='bg', kind='animation', title='K046 чорний фон', start=10, duration=5),
             dict(id='blur', kind='image', title='K046 фон', start=10, duration=5, width=1, height=1),
             dict(id='photo', kind='image', title='K046 кадр', start=10, duration=5, width=.8, height=.9, scale=1.03,
                  keyframes=[{'time': 0, 'scale': 1.03}, {'time': 5, 'scale': 1.18}], easing='ease_in_out'),
             dict(id='dot', kind='image', title='K046 акцент коло', start=11, duration=2, width=.1, height=.1),
             dict(id='code', kind='animation', content_type='code', title='K046 моушн', start=10.5, duration=4, code=code)]
    return dict(id='p' * 24, width=1920, height=1080, fps=25, tracks=[dict(id='l', clips=clips)],
                scene_groups=[dict(id='g', clip_ids=[c['id'] for c in clips])])


class FollowTest(unittest.TestCase):
    def test_the_frames_picture_is_chosen_not_its_backing_or_accents(self):
        p = project('function draw(ctx,t,info){const [x,y]=info.pin(.5,.5);}')
        follow = motion_code.follow_of(p, p['tracks'][0]['clips'][-1])
        self.assertEqual(follow['keyframes'][-1]['scale'], 1.18)
        self.assertEqual(follow['width'], .8)

    def test_only_code_that_pins_carries_the_picture_in_its_cache_key(self):
        pinned = project('function draw(ctx,t,info){info.onPhoto(ctx);}')
        plain = project('function draw(ctx,t,info){}')
        self.assertIn('follow', motion_code.spec(pinned, pinned['tracks'][0]['clips'][-1]))
        self.assertNotIn('follow', motion_code.spec(plain, plain['tracks'][0]['clips'][-1]))


if __name__ == '__main__':
    unittest.main()
