const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'..','channel-voice-lab.js'),'utf8'),context);
const settings={provider:'elevenlabs',language:'ru',text:'A sample.',model:'eleven_v4_turbo',delivery:'conversational',stability:.5,similarity_boost:.75};
const ready={settings,cached_sample:true,sample_matches_settings:true};
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
