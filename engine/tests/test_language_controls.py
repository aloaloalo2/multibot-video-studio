import unittest
from preview_js import run

class LanguageControlsTest(unittest.TestCase):
    def test_default_save_is_scoped_to_the_open_language(self):
        result=run(['langSaveDefaults'], """
(async()=>{
await langSaveDefaults('project','es',button);
console.log(JSON.stringify({sent,defaults:langData.defaults,drawn,busy:button.attrs['aria-busy'],saving:button.dataset.saving}));
})();
""", prelude="""
const state={project:{id:'project'},view:'langs'},langData={},sent=[];let drawn=0;
const button={dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}};
async function api(url,method,body){sent.push({url,method,body});return {by_language:{es:true,uk:false}};}
function drawLangs(){drawn++;}function showLangJob(){}function langNote(){throw Error('unexpected failure');}
""")
        self.assertEqual(result['sent'],[{'url':'/api/projects/project/languages/defaults','method':'POST','body':{'code':'es'}}])
        self.assertEqual(result['defaults']['by_language'],{'es':True,'uk':False})
        self.assertEqual(result['drawn'],1)
        self.assertNotIn('busy',result)
        self.assertNotIn('saving',result)

    def test_ready_sample_plays_directly_updates_time_and_pauses_without_generating(self):
        result=run(['langBindSamplePlayback'], """
(async()=>{
const toggle=langBindSamplePlayback(audio,button,label);
const before=label.textContent;await toggle();audio.currentTime=12;audio.emit('timeupdate');
const playing={label:label.textContent,icon:button.innerHTML,pressed:button.attrs['aria-pressed']};
await toggle();const paused=button.innerHTML;
audio.ended=true;audio.currentTime=60;audio.emit('ended');await toggle();
console.log(JSON.stringify({before,playing,paused,restartedAt:audio.currentTime,plays,otherPaused,errors}));
})();
""", prelude="""
const playIcon='play',pauseIcon='pause';let plays=0,otherPaused=0,errors=[];
const button={attrs:{},setAttribute(k,v){this.attrs[k]=v;}},label={};
const audio={paused:true,ended:false,duration:60,currentTime:0,events:{},
 addEventListener(n,f){(this.events[n]??=[]).push(f);},emit(n){for(const f of this.events[n]||[])f();},
 async play(){plays++;this.paused=false;this.ended=false;this.emit('play');this.emit('playing');},
 pause(){this.paused=true;this.emit('pause');}};
const document={querySelectorAll:()=>[audio,{pause(){otherPaused++;}}]};
function clock(s){return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
function langNote(b,s){errors.push(s);}
""")
        self.assertEqual(result['before'],'0:00 / 1:00')
        self.assertEqual(result['playing'],{'label':'0:12 / 1:00','icon':'pause','pressed':'true'})
        self.assertEqual(result['paused'],'play')
        self.assertEqual(result['restartedAt'],0)
        self.assertEqual((result['plays'],result['otherPaused']),(2,2))
        self.assertEqual(result['errors'],[])

    def test_sample_playback_failure_is_visible_and_loading_is_cleared(self):
        result=run(['langBindSamplePlayback'], """
(async()=>{
await langBindSamplePlayback(audio,button,label)();
console.log(JSON.stringify({label:label.textContent,busy:button.attrs['aria-busy'],icon:button.innerHTML,errors}));
})();
""",prelude="""
const playIcon='play',pauseIcon='pause',errors=[];
const button={attrs:{},setAttribute(k,v){this.attrs[k]=v;}},label={};
const audio={paused:true,ended:false,currentTime:0,duration:NaN,addEventListener(){},async play(){this.error={code:4};throw Error('Audio unavailable');}};
const document={querySelectorAll:()=>[]};function clock(){return '00:00';}function langNote(b,s){errors.push(s);}
""")
        self.assertEqual(result['busy'],'false')
        self.assertEqual(result['icon'],'play')
        self.assertEqual(result['label'],'Помилка відтворення')
        self.assertIn('Audio unavailable',result['errors'][0])

    def test_ready_current_audio_shows_status_and_stale_audio_still_offers_rebuild(self):
        result=run(['langVoiceStatus'], """
const voice={files:{voice:true},voice_current:true,voice:{provider:'elevenlabs'},saved_mix:{state:'saved'}};
console.log(JSON.stringify([
langVoiceStatus(voice,{id:'elevenlabs'}),
langVoiceStatus({...voice,saved_mix:{state:'outdated'}},{id:'elevenlabs'}),
langVoiceStatus({...voice,voice_current:false},{id:'elevenlabs'}),
langVoiceStatus(voice,{id:'fishaudio'}),
langVoiceStatus({...voice,voice_language_check:{state:'wrong_language'}},{id:'elevenlabs'})]));
""")
        self.assertEqual(result,['Озвучку збережено ✓','Озвучка готова ✓','','',''])

    def test_slow_old_project_response_cannot_replace_open_project(self):
        result=run(['loadLangs','langStart'], """
(async()=>{
const load=loadLangs('first');state.project.id='second';finish({items:['old']});await load;
const afterLoad=langData.project;
state.project.id='first';const start=langStart('first','voice','es');state.project.id='second';
finish({job:{status:'running',code:'es'}});await start;
console.log(JSON.stringify({afterLoad,afterStart:langData.project,draws}));
})();
""",prelude="""
let finish,draws=0,langData={project:'second',provider:'elevenlabs'};
const state={project:{id:'first'},view:'langs'};
function api(){return new Promise(resolve=>finish=resolve);}function drawLangs(){draws++;}function langBusy(){return false;}
""")
        self.assertEqual(result,{'afterLoad':'second','afterStart':'second','draws':0})

    def test_reference_upload_tracks_bytes_then_processing_and_cleans_up_failure(self):
        result=run(['langSendExample'], """
(async()=>{
const upload=langSendExample('/voice','data','voice.mp4','',holder);
const start={...langUploads.get('/voice')};xhr.upload.onprogress({lengthComputable:true,loaded:50,total:100});
const halfway={...langUploads.get('/voice')};xhr.upload.onload();
const processing={...langUploads.get('/voice')};xhr.status=500;xhr.responseText='{"error":"conversion failed"}';xhr.onload();
let error;try{await upload;}catch(e){error=e.message;}
console.log(JSON.stringify({start,halfway,processing,error,remaining:langUploads.size,painted}));
})();
""",prelude="""
const langUploads=new Map(),holder={dataset:{}};let xhr,painted=0;
class XMLHttpRequest {constructor(){xhr=this;this.upload={};}open(){}setRequestHeader(){}send(){}}
function langPaintUpload(){painted++;}function showLangJob(){}
""")
        self.assertEqual(result['start']['percent'],0)
        self.assertEqual(result['halfway']['percent'],50)
        self.assertTrue(result['processing']['processing'])
        self.assertEqual(result['error'],'conversion failed')
        self.assertEqual(result['remaining'],0)
        self.assertGreaterEqual(result['painted'],4)

    def test_flag_checkbox_remembers_channel_choice_but_shared_languages_stay_unchecked_and_disabled(self):
        html=run(['langThumbnailFlag'], """
console.log(JSON.stringify([
langThumbnailFlag({flag_country:{name:'Польща',flag:'🇵🇱'}}),
langThumbnailFlag({flag_country:null})]));
""",prelude="const langData={thumbnail_options:{add_flag:true}};function esc(x){return x;}")
        self.assertIn('checked',html[0])
        self.assertNotIn(' disabled',html[0])
        self.assertIn('Адаптувати під країну 🇵🇱',html[0])
        self.assertNotIn(' checked',html[1])
        self.assertIn(' disabled',html[1])
        self.assertIn('немає однозначного прапора',html[1])
    def test_review_links_show_time_and_both_directions_of_tempo(self):
        html=run(['langFitReview'], """
console.log(JSON.stringify(langFitReview({review:[
{index:0,start:20,end:24,speed:1.1,shift:0,text:'Words'},
{index:1,start:40,end:44,speed:.9,shift:1,text:'More'}]})));
""",prelude="function esc(x){return x;}function clock(x){return '00:'+x;}")
        self.assertIn('Прискорено на 10%',html)
        self.assertIn('Уповільнено на 10%',html)
        self.assertIn('data-start="20"',html)
        self.assertIn('Зміщено на 1,0 с пізніше',html)
    def test_voice_reference_and_model_are_visible_before_translation(self):
        result=run(['langCard','langTranslationInfo'], """
const card=langCard('project',{code:'ru',text:'',prices:{},files:{samples:[],voice:false,thumbnail:false}},
 {id:'elevenlabs',name:'ElevenLabs',configured:true,engines:[{id:'eleven_v4_turbo',name:'Eleven v4 Turbo'}],engine:'eleven_v4_turbo'});
console.log(JSON.stringify({reference:card.innerHTML.includes('lang-reference-panel'),model:card.innerHTML.includes('Eleven v4 Turbo'),synthesize:card.innerHTML.includes('lang-voice-run'),off:card.innerHTML.includes('lang-step is-off')}));
""", prelude="""
const langDrafts={},langData={source:{voice:true},defaults:{saved:true},providers:[{id:'elevenlabs',name:'ElevenLabs'}],openrouter:true,thumbnail:false};
const document={createElement:()=>({dataset:{},innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[]})};
function esc(s){return String(s??'');}function langOwnBlock(){return 'voice-reference';}function langOwnWire(){}function langWireReview(){}function langFitReview(){return "";}function langApplyQuality(){}
const langIcons={redo:''};
""")
        self.assertEqual(result,{'reference':True,'model':True,'synthesize':False,'off':False})

    def test_synthesis_actions_disappear_while_whole_voice_runs(self):
        result=run(['showLangJob'], """
showLangJob();const during=row.hidden;
jobs[0].status='done';showLangJob();console.log(JSON.stringify([during,row.hidden]));
""", prelude="""
const row={hidden:false,querySelector:()=>null},jobs=[{kind:'voice',code:'es',status:'running'}];
const state={project:{id:'project'}},langUploads=new Map();
const steps=[0,1,2].map(()=>({querySelector:()=>null}));
const card={dataset:{code:'es'},querySelector:()=>row,querySelectorAll:s=>s==='.lang-step'?steps:[]};
const document={querySelectorAll:s=>s==='#project-langs .lang-card[data-code]'?[card]:[]};
function langJobs(){return jobs;}
""")
        self.assertEqual(result,[True,False])
