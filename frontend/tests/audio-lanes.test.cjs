const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=file=>fs.readFileSync(path.join(__dirname,'..',file),'utf8');
const groups=read('groups.js'),universal=read('universal.js'),plan=read('plan.js'),director=read('director.js');
function load(source,from,to,globals={}){const c=vm.createContext(globals);vm.runInContext(source.slice(source.indexOf(from),source.indexOf(to)),c);return c;}

test('sequential and overlapping effects share one row without changing original audio or voice',()=>{
  const c=load(groups,'function compactSoundRows(','function appendGroupedMediaClip(');
  const entry=(title,start,id)=>{const clip={id,title,start,duration:.6,kind:'audio'};return {clip,layer:{id:'layer-'+id,clips:[clip]},z:start};};
  const voice=entry('Озвучка',0,'voice'),music=entry('Музыка',0,'music');
  const cues=Array.from({length:30},(_,i)=>entry('Звук ролика · pop '+i,i,'c'+i));
  cues.push(entry('Звук переходу · 1 → 2 · tr_air',.2,'transition'));
  const input=[voice,music,...cues],before=JSON.stringify(input),rows=c.compactSoundRows(input);
  assert.equal(rows.length,3);assert.equal(rows[0],voice);
  assert.equal(rows.find(r=>r.soundFamily==='effects').soundItems.length,31);
  assert.equal(rows.find(r=>r.soundFamily==='music').soundItems[0],music);
  assert.equal(JSON.stringify(input),before); // grouping never edits, stretches, mixes, or rebuy audio
});

test('muting a compact sound row affects only its audio layers in one undoable action',()=>{
  let listener;const calls=[],button={setAttribute(){},addEventListener:(event,fn)=>listener=fn};
  const c=load(universal,'function addLayerSoundControl(','function layerTime(',{
    document:{createElement:()=>button},action:(...args)=>{calls.push(args);return Promise.resolve();}});
  c.addLayerSoundControl({append(){},closest:()=>null},[{id:'a',clips:[{kind:'audio'}]},{id:'b',clips:[{kind:'audio'}],muted:true}], 'Звук ролика');
  listener({stopPropagation(){}});
  assert.equal(calls[0][0],'batch');assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1].actions)),[
    {type:'set_layer_mute',payload:{layer_id:'a',muted:true}},{type:'set_layer_mute',payload:{layer_id:'b',muted:true}}]);
});

test('original narration requires a configured reference or selected HeyGen voice',()=>{
  const c=load(plan,'function channelVoiceAvailable(','function renderNarrationGeneration(');
  vm.runInContext(read('channel-voice-lab.js'),c);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'elevenlabs',model:'eleven_v4_turbo'}}),false);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'fishaudio'},reference:{filename:'sample.mp3'}}),true);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'heygen'},reference:{filename:'uncloned.mp3'}}),false);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'heygen',heygen_voice_id:'selected'}}),true);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'fishaudio',fish_voice_id:'selected'}}),true);
  assert.equal(c.channelVoiceAvailable({settings:{provider:'elevenlabs',eleven_voice_id:'selected'}}),true);
});

test('missing voice disables generation while a running narration can always be stopped',()=>{
  const row={},button={setAttribute(){}},c=load(plan,"  function actionState(mode='idle')",'  function renderRunning(job)',{
    voiceReady:false,text:{value:'A complete scenario'},button,box:{classList:{toggle(){}},querySelector:()=>row},panel:{querySelector:()=>null},exportSpinner:'spinner'});
  c.actionState();assert.equal(button.disabled,true);assert.equal(row.hidden,true);
  c.actionState('running');assert.equal(button.disabled,false);assert.equal(row.hidden,false);
  c.actionState('cancelling');assert.equal(button.disabled,true);
  c.voiceReady=true;c.actionState();assert.equal(button.disabled,false);assert.equal(row.hidden,false);
});

test('creation resumes after existing work or a previous attempt',()=>{
  const c=load(director,'function productionStartLabel(','function buildMake(');
  assert.equal(c.productionStartLabel(null,0),'Почати створення ролика');
  for(const request of [{status:'failed'},{status:'done'},{status:'requested'}])assert.equal(c.productionStartLabel(request),'Продовжити створення ролика');
  assert.equal(c.productionStartLabel(null,3),'Продовжити створення ролика');
});


test('script count measures the actual text and updates its muted heading',()=>{
  const c=load(plan,'function scriptWordCount(','const voiceScriptDraft=');
  assert.equal(c.scriptWordCount('Hello, world!'),2);
  assert.equal(c.scriptWordCount("П'ять слів тут? Насправді лише шість."),6);
  assert.equal(c.scriptWordCount('123 ... !'),0);
  const badge={},panel={querySelector:()=>badge};
  c.updateScriptWordCount(panel,'One two three');assert.equal(badge.textContent,'3 слова');
  c.updateScriptWordCount(panel,'One two');assert.equal(badge.textContent,'2 слова');
});

test('missing channel voice defaults to upload while active synthesis stays on its stop controls',()=>{
  const c=load(plan,'function narrationInitialMode(','function narrationChoices(',{
    channelVoiceAvailable:p=>p.settings?.provider==='heygen'?!!p.settings.heygen_voice_id:!!p.reference});
  assert.equal(c.narrationInitialMode({source:'script'},{settings:{provider:'elevenlabs'}}),'file');
  assert.equal(c.narrationInitialMode({source:'file'},{reference:{filename:'voice.mp3'}}),'file');
  assert.equal(c.narrationInitialMode({source:'script'},{reference:{filename:'voice.mp3'}}),'script');
  assert.equal(c.narrationInitialMode({job:{status:'running'}},{settings:{provider:'heygen'}}),'script');
  assert.equal(c.narrationInitialMode({job:{status:'cancelling'}},null),'script');
  assert.equal(c.narrationInitialMode({source:'script'},null),'script');
  assert.equal(c.narrationInitialMode({job:{status:'done',asset_id:'saved'}},{settings:{provider:'heygen'}}),'script');
  const voice={settings:{provider:'heygen',heygen_voice_id:'saved'}};
  assert.equal(c.narrationInitialMode({},voice,'Saved script.'),'script');
  assert.equal(c.narrationInitialMode({},voice,'   '),null);
  assert.equal(c.narrationInitialMode({source:'file'},voice,'Saved script.'),'file');
  assert.equal(c.narrationInitialMode({},{settings:{provider:'heygen'}},'Saved script.'),'file');
});
