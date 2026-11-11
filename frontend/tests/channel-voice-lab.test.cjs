const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({esc:String});
vm.runInContext(fs.readFileSync(path.join(__dirname,'..','audio-effects.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8'),context);
const settings={provider:'elevenlabs',language:'ru',text:'A sample.',model:'eleven_v4_turbo',delivery:'conversational',stability:.5,similarity_boost:.75};
const ready={settings,cached_sample:true,sample_matches_settings:true};
test('a matching ready sample replaces the action, changed synthesis settings restore it, and reverting reuses it',()=>{
  const s={...settings,provider:'heygen',heygen_model:'heygen-voice-1-turbo-free',heygen_voice_id:'voice',heygen_expressiveness:.85};
  const saved={...ready,settings:s,job:{status:'done'}};
  assert.equal(context.voiceLabSampleState(s,saved).ready,true);
  for(const [field,value] of [['text','Different text.'],['heygen_expressiveness',.7],['heygen_model','heygen-voice-1'],['heygen_voice_id','different-voice']]){
    assert.equal(context.voiceLabSampleState({...s,[field]:value},saved).ready,false);
    assert.equal(context.voiceLabSampleState({...s,[field]:s[field]},saved).ready,true);
  }
  assert.equal(context.voiceLabSampleState({...s,speed:.9,reverb:{enabled:true},room_noise:{enabled:true}},saved).ready,true);
});
test('a running or failed request without usable audio cannot be presented as ready',()=>{
  assert.equal(context.voiceLabSampleState(settings,{...ready,job:{status:'running'}}).ready,false);
  assert.equal(context.voiceLabSampleState(settings,{...ready,local_preview:'/dry.mp3',job:{status:'running'}}).ready,false);
  assert.equal(context.voiceLabSampleState(settings,{settings,job:{status:'failed'}}).ready,false);
  assert.equal(context.voiceLabSampleState(settings,{settings,local_preview:'/dry.mp3'}).ready,true);
});
test('ready rendering uses one named player without a duplicate status and restores it after reverting edits',()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8');
  let selected={...settings};
  const output={children:[],append(child){this.children.push(child);}},messages=[];
  const c=vm.createContext({
    read:()=>selected,data:{...ready,job:{status:'done',fingerprint:'sample-key'}},
    voiceLabSampleState:context.voiceLabSampleState,preparedPlayer(){},localSample(){},
    box:{querySelector:()=>output},clearSample(){output.children=[];},
    voicePlayer:(_id,url,options)=>({url,options}),document:{createElement:()=>({})},
    message:text=>messages.push(text),estimate(){},base:'/voice-lab',
    api:()=>{throw Error('editing must not start synthesis');}
  });
  vm.runInContext(source.slice(source.indexOf('  const sample=()=>{'),source.indexOf('  const poll=async()=>{'))+'\nthis.refreshSample=sample;',c);
  c.refreshSample();
  assert.equal(output.children.filter(child=>child.url).length,1);
  assert.equal(output.children[0].options.filename,'Зразок голосу готовий');
  assert.equal(messages.at(-1),'');
  selected={...settings,stability:.9};c.refreshSample();
  assert.equal(output.children.length,0);
  assert.match(messages.at(-1),/Налаштування змінено/);
  selected={...settings};c.refreshSample();
  assert.equal(output.children.filter(child=>child.url).length,1);
  assert.equal(messages.at(-1),'');
});
test('saved voice IDs work without local reference files and invalidate other voice takes',()=>{
  for(const [provider,field] of [['fishaudio','fish_voice_id'],['elevenlabs','eleven_voice_id'],['heygen','heygen_voice_id']]){
    const s={...settings,provider,[field]:'saved-id'};
    assert.equal(context.voiceLabVoiceId(s),'saved-id');
    assert.equal(context.voiceLabSampleState({...s,[field]:'another-id'},{...ready,settings:s}).cached,false);
  }
  const source=fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8');
  assert.match(source,/details class="voice-lab-advanced voice-id-details"/);
  assert.doesNotMatch(source,/voice-id-details" open/);
  assert.match(source,/data-copy-voice/);
  assert.match(source,/base\+'\/fish-clone'/);
});
test('Starfish sample identity and duration quote use only its active controls',()=>{
  const s={...settings,provider:'heygen',heygen_model:'starfish',heygen_voice_id:'voice',speed:1,heygen_starfish_speed:1,heygen_starfish_ssml:false,heygen_starfish_locale:''};
  const saved={...ready,settings:s};
  for(const [field,value] of [['heygen_starfish_speed',1.5],['heygen_starfish_ssml',true],['heygen_starfish_locale','uk-UA']])assert.equal(context.voiceLabSampleState({...s,[field]:value},saved).cached,false);
  assert.equal(context.voiceLabSampleState({...s,heygen_expressiveness:.9},saved).cached,true);
  const models=[{id:'starfish',rate:.12/900}];
  assert.ok(Math.abs(context.voiceLabHeygenCost({...s,text:'x'.repeat(900)},models)-.12)<1e-10);
  assert.ok(Math.abs(context.voiceLabHeygenCost({...s,text:'x'.repeat(900),heygen_starfish_speed:2},models)-.06)<1e-10);
});
test('changed stability or similarity cannot play an old cached sample, including a late poll',()=>{
  for(const field of ['stability','similarity_boost']){
    const changed={...settings,[field]:.95};
    assert.equal(context.voiceLabSampleState(changed,ready).cached,false);
    assert.equal(context.voiceLabSampleState(changed,ready).matches,false);
  }
  assert.equal(context.voiceLabSampleState(settings,ready).cached,true);
  assert.equal(context.voiceLabSampleState(settings,{...ready,sample_matches_settings:false}).matches,false);
});
test('changing provider selects a separate sample and inactive controls do not affect Fish',()=>{
  const fish={...settings,provider:'fishaudio',fish_engine:'s2.1-pro-free',temperature:.7,top_p:.7};
  assert.equal(context.voiceLabSampleState(fish,ready).matches,false);
  assert.equal(context.voiceLabSampleState({...fish,stability:.9},{...ready,settings:fish}).matches,true);
});
test('removing a stale sample stops its audio before discarding the player',()=>{
  const events=[];
  context.voiceLabClearSample({querySelectorAll:()=>[{pause(){events.push('pause');},removeAttribute(k){events.push(k);},load(){events.push('load');}}],replaceChildren(){events.push('remove');}});
  assert.deepEqual(events,['pause','src','load','remove']);
});
test('reference cleanup, Fish chunk length and Eleven delivery instructions select new samples',()=>{
  const clean={...settings,noise_cleanup:true,direction:''};
  const data={...ready,settings:clean};
  assert.equal(context.voiceLabSampleState({...clean,noise_cleanup:false},data).cached,false);
  assert.equal(context.voiceLabSampleState({...clean,direction:'Warm conversational tone'},data).cached,false);
  const fish={...clean,provider:'fishaudio',chunk_length:200,fish_engine:'s2.1-pro-free',temperature:.7,top_p:.7};
  assert.equal(context.voiceLabSampleState({...fish,chunk_length:300},{...data,settings:fish}).cached,false);
});
test('HeyGen expression change invalidates the ready sample while unrelated sliders do not',()=>{
  const heygen={...settings,provider:'heygen',heygen_model:'heygen-voice-1-turbo-free',heygen_voice_id:'voice',speed:1,heygen_expressiveness:.5};
  const saved={...ready,settings:heygen};
  assert.equal(context.voiceLabSampleState({...heygen,heygen_expressiveness:.85},saved).cached,false);
  assert.equal(context.voiceLabSampleState({...heygen,stability:.85},saved).cached,true);
});

test('voice tempo uses one-percent steps with visible ticks from 87 to 105',()=>{
  const html=context.voiceTempoRange('tempo',87,'speed');
  assert.match(html,/min="87" max="105" step="1" value="87"/);
  assert.equal((html.match(/<i(?:>| )/g)||[]).length,19);
  assert.match(html,/class="tempo-normal"/);
  assert.equal(context.voiceTempoPercent(80),87);
  assert.equal(context.voiceTempoPercent(110),105);
  const plan=fs.readFileSync(path.join(__dirname,'..','plan.js'),'utf8');
  assert.match(plan,/voiceTempoRange\("narration-speed-range",current\)/);
});
