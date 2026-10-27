import copy,importlib.util,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import joins

class JoinTest(unittest.TestCase):
    def test_full_frame_text_stays_visible_above_incoming_transition(self):
        for style in ('paper_tear','slide_up'):
            with self.subTest(style=style):
                p=self.project();p['tracks'][1]['clips'][0]['text_role']='full_frame'
                p['tracks'].append(dict(id='brand',clips=[dict(id='brand',kind='text',start=0,duration=2,text='Brand')]))
                p['scene_groups'].append(dict(id='brand',role='overlay',clip_ids=['brand']))
                joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type=style,duration=.3))
                before=copy.deepcopy(p)
                layers=[dict(id=t['id'],z=i,clips=[{**c,'type':c['kind']} for c in t['clips']]) for i,t in enumerate(p['tracks'])]
                joins.transport(p,layers)
                text=next(layer for layer in layers if any(c['id']=='b' for c in layer['clips']))
                self.assertNotIn('join_in',text['clips'][0]);self.assertLess(text['z'],layers[2]['z'])
                self.assertGreater(text['z'],layers[1]['z'])
                if style=='paper_tear':
                    graphic=next(layer for layer in layers if layer['id'].startswith('graphic-'))
                    self.assertGreater(text['z'],graphic['z'])
                self.assertEqual(p,before)
    def test_all_cinematic_presets_are_valid_and_can_be_replaced_or_removed(self):
        styles=[style for style,config in joins.GRAPHIC_PRESETS.items() if config.get('kind')=='cinematic']
        self.assertEqual(len(styles),15)
        for style in styles:
            with self.subTest(style=style):
                p=self.project();original=copy.deepcopy(p['tracks'])
                joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type=style,duration=.5))
                self.assertEqual(p['join_transitions'][0]['type'],style)
                layers=[dict(z=i,clips=[{**c,'type':c['kind']} for c in t['clips']]) for i,t in enumerate(p['tracks'])]
                joins.transport(p,layers)
                self.assertEqual(layers[-1]['clips'][0]['graphic_style'],style)
                joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='cut',duration=0))
                self.assertFalse(p['join_transitions']);self.assertEqual(p['tracks'],original)
    def test_graphic_overlay_is_exported_below_permanent_brand(self):
        p=self.project();p['tracks'].append(dict(id='brand',clips=[dict(id='brand',kind='text',start=0,duration=2,text='Brand')]))
        p['scene_groups'].append(dict(id='brand',role='overlay',clip_ids=['brand']))
        joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='ribbon_tricolor',duration=.3))
        layers=[dict(z=i,clips=[{**c,'type':c['kind']} for c in t['clips']]) for i,t in enumerate(p['tracks'])]
        joins.transport(p,layers)
        self.assertEqual(layers[-1]['clips'][0]['graphic_style'],'ribbon_tricolor')
        self.assertLess(layers[-1]['z'],layers[2]['z']);self.assertGreater(layers[-1]['z'],layers[1]['z'])
    def project(self):return dict(fps=25,tracks=[dict(id='a',clips=[dict(id='a',kind='animation',content_type='shape',start=0,duration=1)]),dict(id='b',clips=[dict(id='b',kind='text',start=1,duration=1,text='B')])],scene_groups=[dict(id='a',role='scene',clip_ids=['a']),dict(id='b',role='scene',clip_ids=['b'])])
    def test_only_real_edges_accept_and_record_transition(self):
        p=self.project();joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='slide_left',duration=.3))
        self.assertEqual(p['join_transitions'][0]['seam'],1)
        bad=self.project();bad['tracks'][1]['clips'][0]['start']=1.5
        with self.assertRaises(ValueError):joins.set_transition(bad,dict(from_ref='group:a',to_ref='group:b',type='crossfade',duration=.3))
        self.assertNotIn('join_transitions',bad)
    def test_transport_keeps_editable_times_and_extends_only_visual_handles(self):
        p=self.project();joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='crossfade',duration=.3));before=copy.deepcopy(p['tracks'])
        layers=[dict(clips=[{**c,'type':c['kind']} for c in t['clips']]) for t in p['tracks']];joins.transport(p,layers)
        self.assertEqual(p['tracks'],before);self.assertEqual(layers[0]['clips'][0]['duration'],1.3);self.assertIn('join_in',layers[1]['clips'][0])
        joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='cut',duration=.3));self.assertFalse(p['join_transitions'])
    def test_broken_edge_is_removed_when_a_frame_moves(self):
        p=self.project();joins.set_transition(p,dict(from_ref='group:a',to_ref='group:b',type='zoom_in',duration=.3));p['tracks'][1]['clips'][0]['start']=3;joins.reconcile(p);self.assertFalse(p['join_transitions'])

if __name__=='__main__':unittest.main()
