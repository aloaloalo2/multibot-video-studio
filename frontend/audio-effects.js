// Local audition uses the very same impulse files as the saved audio.
const voiceRoomPresets=[['office','Кабінет лікаря'],['studio','Студія'],['room','Кімната'],['hall','Зала']];
function voiceReverbValue(value={}){return {enabled:!!value?.enabled,preset:value?.preset||'office',amount:value?.amount??15};}
function voiceReverbKey(value){const v=voiceReverbValue(value);return v.enabled&&v.amount>0?JSON.stringify(v):'';}
function voiceReverbGains(value,version=4){const v=voiceReverbValue(value),wet=version>=4&&v.preset==='office'?.10*(v.amount/100)**.8:v.amount/100*.22;return [1-wet*(version>=4&&v.preset==='office'?.25:1),wet];}
const voiceNoisePresets=[['office','Тихий кабінет'],['room','Тиха кімната'],['soft','М’який фон'],['city','Місто вдалині']];
function voiceNoiseValue(value={}){return {enabled:!!value?.enabled,preset:value?.preset||'office',amount:value?.amount??35};}
function voiceNoiseKey(value){const v=voiceNoiseValue(value);return v.enabled&&v.amount>0?JSON.stringify(v):'';}
function voiceNoiseGain(value,version=3){const n=voiceNoiseValue(value);return n.amount>0?10**(((version<3?-66:-60)+n.amount*(version<3?.18:.3))/20)/.1:0;}
function voiceReverbControls(value,noise){
  const v=voiceReverbValue(value),n=voiceNoiseValue(noise);
  const roomIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M5 8v8m5-11v14m5-12v10m5-7v4" stroke-linecap="round"/></svg>';
  const noiseIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 12h3l2-5 4 10 3-8 2 3h4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const listen='<button type="button" class="voice-noise-listen" aria-label="Прослухати лише фон" aria-pressed="false" title="Прослухати лише фон із вибраною гучністю"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg></button>';
  return `<div class="voice-reverb"><section class="voice-effect-card"><label class="voice-effect-toggle"><input type="checkbox" data-reverb="enabled" ${v.enabled?'checked':''}>${roomIcon}<span>Реверберація</span></label><div class="voice-reverb-options" ${v.enabled?'':'hidden'}><label>Простір<select data-reverb="preset">${voiceRoomPresets.map(([id,name])=>`<option value="${id}" ${id===v.preset?'selected':''}>${name}</option>`).join('')}</select></label><label>Сила<span><input type="range" min="0" max="100" step="1" value="${v.amount}" data-reverb="amount" aria-label="Сила реверберації"><output>${v.amount}%</output></span></label></div></section><section class="voice-effect-card"><div class="voice-effect-head"><label class="voice-effect-toggle"><input type="checkbox" data-noise="enabled" ${n.enabled?'checked':''}>${noiseIcon}<span>Фоновий шум мікрофона</span></label>${listen}</div><div class="voice-noise-options" ${n.enabled?'':'hidden'}><label>Фон<select data-noise="preset">${voiceNoisePresets.map(([id,name])=>`<option value="${id}" ${id===n.preset?'selected':''}>${name}</option>`).join('')}</select></label><label class="voice-noise-level">Гучність<span><input type="range" min="0" max="100" step="1" value="${n.amount}" data-noise="amount" aria-label="Гучність фонового шуму"><output>${n.amount}%</output></span></label></div></section></div>`;
}
function readVoiceReverb(box){return {enabled:box.querySelector('[data-reverb=enabled]').checked,preset:box.querySelector('[data-reverb=preset]').value,amount:Number(box.querySelector('[data-reverb=amount]').value)};}
function readVoiceNoise(box){return {enabled:box.querySelector('[data-noise=enabled]').checked,preset:box.querySelector('[data-noise=preset]').value,amount:Number(box.querySelector('[data-noise=amount]').value)};}
function syncVoiceReverb(box){
  const v=readVoiceReverb(box),n=readVoiceNoise(box);box.querySelector('.voice-reverb-options').hidden=!v.enabled;
  box.querySelector('[data-reverb=amount]').closest('label').querySelector('output').textContent=v.amount+'%';
  box.querySelector('.voice-noise-options').hidden=!n.enabled;
  box.querySelector('[data-noise=amount]').closest('label').querySelector('output').textContent=n.amount+'%';
  return v;
}
let voiceEffectContext;
function voiceAudioContext(){return voiceEffectContext??=new (window.AudioContext||window.webkitAudioContext)();}
const voiceImpulseBuffers=new Map();
function voiceEffectBuffer(preset,version=4){
  const key=preset+'-v'+(version>=4?4:2);
  if(!voiceImpulseBuffers.has(key))voiceImpulseBuffers.set(key,fetch(`/api/audio-effects/${key}.wav`).then(r=>{if(!r.ok)throw Error('Не вдалося завантажити звуковий ефект');return r.arrayBuffer();}).then(data=>voiceEffectContext.decodeAudioData(data)).catch(error=>{voiceImpulseBuffers.delete(key);throw error;}));
  return voiceImpulseBuffers.get(key);
}
function attachVoiceTempo(audio,source,getSpeed,onError=()=>{}){
  let timer,version=0,currentSpeed=1,requested='',ready,pendingPosition=null;
  // A settings tab may still be collapsed when its sample is mounted.
  const alive=()=>audio.isConnected;
  const failed=()=>{audio.removeAttribute('aria-busy');if(alive())onError(Error('Не вдалося підготувати темп зразка'));};
  audio.addEventListener('error',failed);
  const update=()=>{
    const next=Number(getSpeed()),url=source+(source.includes('?')?'&':'?')+'speed='+next.toFixed(6);
    if(!alive()||url===requested)return;
    requested=url;const token=++version;clearTimeout(timer);
    timer=setTimeout(()=>{
      if(!alive()||token!==version)return;
      const position=pendingPosition??audio.currentTime*currentSpeed,at=position/next,playing=!audio.paused;
      pendingPosition=position;
      audio.pause();if(ready)audio.removeEventListener('loadedmetadata',ready);
      ready=()=>{if(token!==version||!alive())return;audio.removeAttribute('aria-busy');audio.currentTime=Math.min(at,Math.max(0,(audio.duration||0)-.01));pendingPosition=null;};
      audio.addEventListener('loadedmetadata',ready,{once:true});audio.setAttribute('aria-busy','true');
      currentSpeed=next;audio.src=url;audio.playbackRate=1;audio.load();
      if(playing&&!audio.closest('[hidden]'))audio.play().catch(error=>{if(token===version&&alive())onError(error);});
    },180);
  };
  update();
  return {update,dispose(){version++;clearTimeout(timer);if(ready)audio.removeEventListener('loadedmetadata',ready);audio.removeEventListener('error',failed);audio.pause();}};
}
function bindVoiceNoisePreview(box,onError=()=>{},processingVersion=4){
  const button=box.querySelector('.voice-noise-listen');
  let source,gain,generation=0,disposed=false;
  const level=()=>{if(gain){const audio=box.querySelector('.voice-local-preview audio');gain.gain.value=voiceNoiseGain(readVoiceNoise(box),processingVersion)*(audio?.muted?0:audio?.volume??1);}};
  const stop=()=>{generation++;if(source){source.onended=null;source.stop();source.disconnect();source=null;}gain?.disconnect();gain=null;button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Прослухати лише фон');button.classList.remove('is-playing','is-loading');};
  const play=async()=>{
    stop();const version=generation;button.classList.add('is-loading');button.setAttribute('aria-pressed','true');
    try{
      const context=voiceAudioContext();await context.resume();
      const buffer=await voiceEffectBuffer('noise-'+readVoiceNoise(box).preset,processingVersion);
      if(disposed||version!==generation||!box.isConnected||box.closest('[hidden]'))return;
      box.querySelectorAll('audio').forEach(audio=>audio.pause());
      source=context.createBufferSource();source.buffer=buffer;gain=context.createGain();
      level();source.connect(gain);gain.connect(context.destination);
      source.onended=stop;source.start(0,0,Math.min(8,buffer.duration));
      button.classList.remove('is-loading');button.classList.add('is-playing');button.setAttribute('aria-label','Зупинити фон');
    }catch(error){if(!disposed&&version===generation){stop();onError(error);}}
  };
  const click=()=>button.getAttribute('aria-pressed')==='true'?stop():play();
  const input=event=>{if(event.target.matches('[data-noise=preset]')&&button.getAttribute('aria-pressed')==='true')play();else level();};
  const voice=event=>{if(event.target.tagName==='AUDIO')stop();};
  button.addEventListener('click',click);box.addEventListener('input',input);box.addEventListener('play',voice,true);box.addEventListener('volumechange',level,true);
  return {dispose(){disposed=true;stop();button.removeEventListener('click',click);box.removeEventListener('input',input);box.removeEventListener('play',voice,true);box.removeEventListener('volumechange',level,true);}};
}
function attachVoiceEffects(audio,getValue,getSpeed=()=>1,onError=()=>{},getNoise=()=>({}),processingVersion=4){
  let source,dry,wet,convolver,limiter,noiseSource,noiseGain,processed,generation=0;
  const alive=()=>audio.isConnected&&!audio.closest('[hidden]');
  const stopNoise=()=>{if(noiseSource){noiseSource.stop();noiseSource.disconnect();noiseSource=null;}};
  const noiseLevel=()=>{
    if(!noiseGain)return;
    const n=voiceNoiseValue(getNoise()),fade=Number.isFinite(audio.duration)?Math.max(0,Math.min(1,(audio.duration-audio.currentTime)/.25)):1;
    noiseGain.gain.value=n.enabled&&n.amount>0&&!audio.paused&&!audio.muted?voiceNoiseGain(n,processingVersion)*audio.volume*fade:0;
  };
  const update=async()=>{
    if(!alive())return;
    const version=++generation,v=voiceReverbValue(getValue()),n=voiceNoiseValue(getNoise());
    audio.preservesPitch=true;audio.playbackRate=getSpeed();
    if(!source)return;
    const effects=!!(v.enabled&&v.amount||n.enabled&&n.amount);
    if(effects!==processed){for(const node of [dry,wet,noiseGain]){node.disconnect();node.connect(effects?limiter:voiceEffectContext.destination);}processed=effects;}
    dry.gain.value=1;wet.gain.value=0;
    if(!n.enabled||!n.amount)stopNoise();
    try{
      const [impulse,noise]=await Promise.all([v.enabled&&v.amount?voiceEffectBuffer(v.preset,processingVersion):null,n.enabled&&n.amount?voiceEffectBuffer('noise-'+n.preset,processingVersion):null]);
      if(version!==generation||!alive()||audio.paused)return;
      if(impulse){if(convolver.buffer!==impulse)convolver.buffer=impulse;[dry.gain.value,wet.gain.value]=voiceReverbGains(v,processingVersion);}
      if(noiseSource&&noiseSource.buffer!==noise)stopNoise();
      if(noise&&!noiseSource){noiseSource=voiceEffectContext.createBufferSource();noiseSource.buffer=noise;noiseSource.loop=true;noiseSource.connect(noiseGain);noiseSource.start();}
      noiseLevel();
    }catch(error){if(version===generation&&alive())onError(error);}
  };
  audio.addEventListener('play',()=>{
    if(!alive()){audio.pause();return;}
    if(!source){
      try{
        voiceAudioContext();
        source=voiceEffectContext.createMediaElementSource(audio);dry=voiceEffectContext.createGain();wet=voiceEffectContext.createGain();
        noiseGain=voiceEffectContext.createGain();noiseGain.gain.value=0;
        convolver=voiceEffectContext.createConvolver();convolver.normalize=false;
        limiter=voiceEffectContext.createDynamicsCompressor();limiter.threshold.value=-.2;limiter.knee.value=0;limiter.ratio.value=20;limiter.attack.value=.001;limiter.release.value=.05;
        source.connect(dry);source.connect(convolver);convolver.connect(wet);limiter.connect(voiceEffectContext.destination);
      }catch(error){onError(error);return;}
    }
    voiceEffectContext.resume().catch(onError);update();
  });
  audio.addEventListener('pause',()=>{generation++;stopNoise();if(dry)dry.gain.value=0;if(wet)wet.gain.value=0;});
  for(const name of ['volumechange','timeupdate'])audio.addEventListener(name,noiseLevel);
  audio.addEventListener('ended',stopNoise);
  return {update,dispose(){generation++;audio.pause();stopNoise();for(const node of [source,dry,wet,convolver,limiter,noiseGain])node?.disconnect();}};
}
