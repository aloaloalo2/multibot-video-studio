import unittest
from preview_js import run


class TrackPositionTest(unittest.TestCase):
    def test_open_properties_and_clip_selection_keep_playhead_position(self):
        result = run(['stackOpen', 'selectUniversalClip'], """
stackOpen({clip,layer:{id:'audio'}});
const properties=state.playhead;
selectUniversalClip('voice');
console.log(JSON.stringify([properties,state.playhead,state.selected]));
""", prelude="""
const state={playhead:120};const clip={id:'voice',start:0};
function universalClips(){return [clip];}function layers(){return [{id:'audio',clips:[clip]}];}
function clearTransitionSelection(){}function seconds(n){return n;}
function renderTimeline(){}function renderInspector(){}function renderPreview(){}
function status(){}function clipLabel(){return 'Voice';}
""")
        self.assertEqual(result, [120, 120, 'voice'])

    def test_double_click_on_track_controls_does_not_open_track(self):
        result = run(['addStackTools'], """
const heading=node();addStackTools(heading,{title:'Voice',clip:{id:'voice'},layer:{id:'audio'}});
for(const control of [true,true,true])heading.events.dblclick({target:{closest:()=>control}});
const controls=opened;
heading.events.dblclick({target:{closest:()=>null}});
console.log(JSON.stringify([controls,opened]));
""", prelude="""
let opened=0;
function node(){return {events:{},replaceChildren(){},append(){},setAttribute(){},addEventListener(k,v){this.events[k]=v;}};}
const document={createElement:node};
function addLayerEyeControl(){}function addLayerSoundControl(){}function addLayerDubControl(){}
function stackOpen(){opened++;}
""")
        self.assertEqual(result, [0,1])
