const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../audio-effects.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(fetcher){
  const events={},requests=[],gains=[],buffers=[];let sourceCount=0;
  const audio={isConnected:true,paused:true,muted:false,volume:1,duration:20,currentTime:0,closest:()=>null,
    addEventListener:(name,fn)=>(events[name]??=[]).push(fn),pause(){this.paused=true;for(const fn of events.pause||[])fn();}};
  const node=()=>({connections:[],connect(other){this.connections.push(other)},disconnect(){this.connections=[]}});
  class AudioContext{
    destination={};resume(){return Promise.resolve()}
    createMediaElementSource(){sourceCount++;return node()}
    createGain(){const result={...node(),gain:{value:1}};gains.push(result);return result}
    createConvolver(){return node()}
    createDynamicsCompressor(){return {...node(),threshold:{},knee:{},ratio:{},attack:{},release:{}}}
    createBufferSource(){const result={...node(),started:0,stopped:0,start(){this.started++},stop(){this.stopped++}};buffers.push(result);return result}
    decodeAudioData(data){return Promise.resolve({...data,duration:16})}
  }
  const c=vm.createContext({window:{AudioContext},fetch:url=>{requests.push(url);return fetcher?fetcher(url):Promise.resolve({ok:true,arrayBuffer:async()=>({url})})}});
  vm.runInContext(code,c);
  const emit=async name=>{audio.paused=name!=='play';for(const fn of events[name]||[])fn();await settle();};
  return {c,audio,emit,requests,gains,buffers,sourceCount:()=>sourceCount};
}
test('local controls expose four rooms and independent microphone ambience, disabled by default',()=>{
  const h=fixture(),html=h.c.voiceReverbControls();
  assert.equal((html.match(/<option/g)||[]).length,8);
  assert.match(html,/Кабінет/);assert.match(html,/Фоновий шум мікрофона/);
  assert.doesNotMatch(html,/checked/);
  assert.equal(h.c.voiceReverbKey({enabled:false,preset:'hall'}),'');
  assert.equal(h.c.voiceNoiseKey({enabled:false,amount:99}),'');
});
test('audition loads only local files after Play and room noise follows mute and pause',async()=>{
  const h=fixture(),settings={enabled:true,preset:'office',amount:60},noise={enabled:true,amount:35};
  const preview=h.c.attachVoiceEffects(h.audio,()=>settings,()=>.87,assert.fail,()=>noise);
  await preview.update();assert.equal(h.requests.length,0);assert.equal(h.audio.playbackRate,.87);
  await h.emit('play');assert.equal(h.sourceCount(),1);assert.equal(h.requests.length,2);
  assert.ok(h.requests.every(url=>url.startsWith('/api/audio-effects/')));
  assert.equal(h.buffers[0].started,1);assert.ok(h.gains[2].gain.value>0);
  h.audio.muted=true; // volume changes keep narration and ambience together
  await preview.update();assert.equal(h.gains[2].gain.value,0);
  noise.preset='room';await preview.update();assert.equal(h.buffers[0].stopped,1);assert.equal(h.requests.length,3);
  await h.emit('pause');assert.equal(h.buffers[1].stopped,1);
  await h.emit('play');assert.equal(h.sourceCount(),1);assert.equal(h.requests.length,3);
  preview.dispose();assert.ok(h.buffers.every(buffer=>buffer.stopped===1));
});
test('a late audio file cannot restart room noise after the preview closes',async()=>{
  let finish;const pending=new Promise(resolve=>finish=resolve);
  const h=fixture(()=>pending),preview=h.c.attachVoiceEffects(h.audio,()=>({enabled:false}),()=>1,assert.fail,()=>({enabled:true,amount:50}));
  await h.emit('play');preview.dispose();h.audio.isConnected=false;
  finish({ok:true,arrayBuffer:async()=>({})});await settle();
  assert.equal(h.buffers.length,0);
});
test('unavailable local preview files report an error without a generation request',async()=>{
  const errors=[],h=fixture(async()=>({ok:false}));
  h.c.attachVoiceEffects(h.audio,()=>({enabled:true,preset:'hall',amount:50}),()=>1,error=>errors.push(error));
  await h.emit('play');assert.equal(errors.length,1);assert.equal(h.requests.length,1);
});
test('disabled processing bypasses the compressor and enabling it never duplicates connections',async()=>{
  const h=fixture(),reverb={enabled:false},noise={enabled:false};
  const preview=h.c.attachVoiceEffects(h.audio,()=>reverb,()=>1,assert.fail,()=>noise);
  await h.emit('play');
  const destination=vm.runInContext('voiceEffectContext.destination',h.c);
  assert.equal(h.gains[0].connections[0],destination);
  noise.enabled=true;noise.amount=100;await preview.update();
  assert.notEqual(h.gains[0].connections[0],destination);assert.equal(h.gains[0].connections.length,1);
  noise.enabled=false;await preview.update();assert.equal(h.gains[0].connections[0],destination);
  preview.dispose();
});
test('background range is audible while remaining below the voice level',()=>{
  const h=fixture();
  assert.ok(Math.abs(20*Math.log10(h.c.voiceNoiseGain({amount:35})*.1)+49.5)<.01);
  assert.ok(Math.abs(20*Math.log10(h.c.voiceNoiseGain({amount:100})*.1)+30)<.01);
  assert.equal(h.c.voiceNoiseGain({amount:0}),0);
  assert.ok(Math.abs(20*Math.log10(h.c.voiceNoiseGain({amount:35},2)*.1)+59.7)<.01);
});
test('doctor office uses its soft response while an older busy server keeps compatible gains',async()=>{
  const h=fixture(),value={enabled:true,preset:'office',amount:25};
  h.c.attachVoiceEffects(h.audio,()=>value,()=>1,assert.fail,()=>({}),4);
  await h.emit('play');assert.ok(h.requests[0].endsWith('office-v4.wav'));
  assert.ok(h.gains[0].gain.value>.99);assert.ok(h.gains[1].gain.value<.035);
  const legacy=h.c.voiceReverbGains(value,3);
  assert.equal(legacy[0],.945);assert.equal(legacy[1],.055);
});
function soloBox(h){
  const handlers={},attributes={'aria-pressed':'false'},classes=new Set();
  const button={setAttribute:(k,v)=>attributes[k]=v,getAttribute:k=>attributes[k],classList:{add:(...a)=>a.forEach(x=>classes.add(x)),remove:(...a)=>a.forEach(x=>classes.delete(x))},
    addEventListener:(k,f)=>handlers[k]=f,removeEventListener:k=>delete handlers[k]};
  const value={enabled:false,preset:'office',amount:35};
  const box={isConnected:true,closest:()=>null,querySelector:q=>q==='.voice-noise-listen'?button:q==='.voice-local-preview audio'?h.audio:q.includes('enabled')?{checked:value.enabled}:q.includes('preset')?{value:value.preset}:{value:value.amount},
    querySelectorAll:()=>[h.audio],addEventListener:(k,f)=>handlers['box:'+k]=f,removeEventListener:k=>delete handlers['box:'+k]};
  return {box,button,value,handlers,classes};
}
test('solo background works with the checkbox off, stops narration, switches recording, and disposes',async()=>{
  const h=fixture(),s=soloBox(h),preview=h.c.bindVoiceNoisePreview(s.box,assert.fail);
  h.audio.paused=false;s.handlers.click();await settle();
  assert.equal(h.requests.length,1);assert.equal(h.buffers[0].started,1);assert.equal(h.audio.paused,true);
  assert.equal(s.button.getAttribute('aria-pressed'),'true');assert.equal(s.value.enabled,false);
  assert.ok(Math.abs(h.gains[0].gain.value-.03349654)<.00001);
  s.value.amount=100;s.handlers['box:input']({target:{matches:()=>false}});
  assert.ok(Math.abs(h.gains[0].gain.value-.31622777)<.00001);
  h.audio.volume=.5;s.handlers['box:volumechange']();assert.ok(Math.abs(h.gains[0].gain.value-.15811388)<.00001);
  h.audio.muted=true;s.handlers['box:volumechange']();assert.equal(h.gains[0].gain.value,0);
  h.audio.muted=false;s.value.amount=0;s.handlers['box:input']({target:{matches:()=>false}});assert.equal(h.gains[0].gain.value,0);
  s.value.preset='city';s.handlers['box:input']({target:{matches:()=>true}});await settle();
  assert.equal(h.buffers[0].stopped,1);assert.match(h.requests[1],/noise-city/);
  preview.dispose();assert.equal(h.buffers[1].stopped,1);assert.equal(s.button.getAttribute('aria-pressed'),'false');
});
test('closing or stopping a loading solo preview cannot start a late recording',async()=>{
  let finish;const pending=new Promise(resolve=>finish=resolve);
  const h=fixture(()=>pending),s=soloBox(h),preview=h.c.bindVoiceNoisePreview(s.box,assert.fail);
  s.handlers.click();await settle();preview.dispose();s.box.isConnected=false;
  finish({ok:true,arrayBuffer:async()=>({})});await settle();assert.equal(h.buffers.length,0);
});
test('tempo audition uses local processed audio at normal playback speed and preserves listening position',async()=>{
  const h=fixture(),timers=[];h.c.setTimeout=f=>(timers.push(f),timers.length);h.c.clearTimeout=()=>{};
  h.audio.setAttribute=()=>{};h.audio.removeAttribute=()=>{};h.audio.removeEventListener=(k,f)=>h.events?.[k]?.splice(h.events[k].indexOf(f),1);
  let loads=0;h.audio.load=()=>loads++;
  const aEvents={};h.audio.addEventListener=(k,f)=>(aEvents[k]??=[]).push(f);
  let speed=.9;const preview=h.c.attachVoiceTempo(h.audio,'/api/channels/channel/voice-lab/preview?v=take',()=>speed,assert.fail);
  timers.shift()();assert.equal(loads,1);assert.match(h.audio.src,/speed=0.900000/);assert.equal(h.audio.playbackRate,1);
  aEvents.loadedmetadata.at(-1)();
  h.audio.currentTime=10;speed=1.05;preview.update();timers.shift()();
  h.audio.currentTime=0; // another setting arrives before this file has loaded
  speed=.95;preview.update();timers.shift()();
  aEvents.loadedmetadata.at(-1)();assert.ok(Math.abs(h.audio.currentTime-10*.9/.95)<.0001);
  preview.dispose();speed=.87;preview.update();preview.dispose();timers.shift()();assert.equal(loads,3);
});
