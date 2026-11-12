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
test('readiness uses only the selected service and HeyGen requires a remote voice',()=>{
  for(const [provider,field] of [['fishaudio','fish_voice_id'],['elevenlabs','eleven_voice_id'],['heygen','heygen_voice_id']]){
    assert.equal(context.voiceLabAvailable({provider,[field]:'saved'},null),true);
    assert.equal(context.voiceLabAvailable({provider},null),false);
    assert.equal(context.voiceLabAvailable({provider},{filename:'reference.mp3'}),provider!=='heygen');
    for(const other of ['fish_voice_id','eleven_voice_id','heygen_voice_id'].filter(key=>key!==field)){
      assert.equal(context.voiceLabAvailable({provider,[other]:'dormant-id'},null),false);
    }
  }
});
test('a transient sample status failure retries only its read and restores the completed sample',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8');
  const block=source.slice(source.indexOf('  const poll=async()=>'),source.indexOf('  const audition=async draft=>'));
  let calls=0,rendered=0,played=0,scheduled;
  const c=vm.createContext({data:{job:{status:'running'}},base:'/voice-lab',current:()=>true,
    api:async(...args)=>{assert.equal(args.length,1);if(!calls++)throw Error('Temporary failure');return {job:{status:'done'}};},
    sample:()=>rendered++,playSample:()=>played++,message(){},setTimeout:(fn,delay)=>{scheduled={fn,delay};return 1;}});
  vm.runInContext(block+'\nthis.readStatus=poll;',c);await c.readStatus();
  assert.equal(scheduled.delay,3000);await scheduled.fn();
  assert.equal(calls,2);assert.equal(rendered,1);assert.equal(played,1);
});
test('channel voice settings can recover from an initial read failure without synthesis',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8');
  const begin=source.indexOf('  const load=async()=>');
  const end=source.indexOf('  await load();',begin)+'  await load();'.length;
  let calls=0,draws=0;const retry={},box={querySelector:()=>retry};
  const c=vm.createContext({box,data:null,base:'/voice-lab',current:()=>true,esc:String,
    api:async(...args)=>{assert.equal(args.length,1);if(!calls++)throw Error('Temporary read error');return {settings:{provider:'fishaudio',fish_voice_id:'saved'}};},draw:()=>draws++});
  await vm.runInContext('(async()=>{'+source.slice(begin,end)+'})()',c);
  assert.match(box.innerHTML,/Temporary read error/);assert.equal(draws,0);
  await retry.onclick({currentTarget:retry});assert.equal(calls,2);assert.equal(draws,1);
  assert.equal(c.data.settings.fish_voice_id,'saved');
});
test('sample preparation cannot be submitted twice while an earlier start is pending',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8');
  const begin=source.indexOf("    box.querySelector('.voice-lab-listen').addEventListener('click',async()=>");
  const end=source.indexOf('    sample();\n    if(data.job',begin);
  let click,finish,calls=0;const button={};
  const c=vm.createContext({box:{querySelector:()=>({addEventListener:(name,fn)=>click=fn,...button})},
    sampleStarting:false,data:{settings:{},job:{}},read:()=>({provider:'fishaudio',fish_voice_id:'saved'}),
    voiceLabAvailable:context.voiceLabAvailable,voiceLabSampleState:()=>({cached:false}),base:'/voice-lab',crypto:{randomUUID:()=> 'fixture-id'},
    api:()=>{calls++;return new Promise(resolve=>finish=resolve);},current:()=>true,
    sample(){},estimate(){},poll(){},playSample(){},message(){},setTimeout(){}});
  vm.runInContext(source.slice(begin,end),c);
  const pending=click();await click();assert.equal(calls,1);assert.equal(c.sampleStarting,true);
  finish({job:{status:'running'}});await pending;assert.equal(c.sampleStarting,false);
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
