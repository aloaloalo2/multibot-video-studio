import unittest
from preview_js import run

class VoiceClipIdentityTest(unittest.TestCase):
    def test_restored_narration_and_music_have_distinct_controls(self):
        result = run(['isVoiceClip'], """
const clips=[
 {kind:'audio',asset_id:'restored',title:'Озвучка',start:0,duration:60},
 {kind:'audio',asset_id:'bed',title:'music_sfx.wav',start:0,duration:60},
 {kind:'audio',asset_id:'bed',title:'Razgon · музика й ефекти',start:0,duration:60},
 {kind:'audio',asset_id:'other',title:'Озвучка',start:20,duration:5},
 {kind:'audio',asset_id:'planned',title:'voice.wav',start:0,duration:60}
];console.log(JSON.stringify(clips.map(isVoiceClip)));
""", prelude="""
const state={plan:{},project:{duration:60,assets:[{id:'bed',name:'music_sfx.wav'}],audio_gain:{bed:1}}};
function voiceAssetId(){return 'planned';}
""")
        self.assertEqual(result, [True,False,False,False,True])

    def test_waveform_follows_the_same_language_and_version_as_audio(self):
        result=run(['audioWaveformUrl'], """
const original=audioWaveformUrl({asset_id:'voice'});
chosen='uk';const uk=audioWaveformUrl({asset_id:'voice'});
chosen='es';const es=audioWaveformUrl({asset_id:'voice'});
const music=audioWaveformUrl({asset_id:'music'});
console.log(JSON.stringify([original,uk,es,music]));
""", prelude="""
let chosen=null;const state={project:{id:'project'}};
function dubbedVoiceUrl(c){return chosen&&c.asset_id==='voice'?`/api/projects/project/languages/${chosen}/file/voice?v=123`:null;}
""")
        self.assertEqual(result, ['/api/projects/project/assets/voice/waveform', '/api/projects/project/languages/uk/waveform?v=123', '/api/projects/project/languages/es/waveform?v=123', '/api/projects/project/assets/music/waveform'])
