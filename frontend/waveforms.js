const waveformRequests=new Map();
function audioWaveformUrl(clip){
  const dubbed=typeof dubbedVoiceUrl==='function'?dubbedVoiceUrl(clip):null;
  return dubbed?dubbed.replace('/file/voice','/waveform'):`/api/projects/${state.project.id}/assets/${clip.asset_id}/waveform`;
}
// the clip's width on the timeline, from its length (measuring each of 325 clips would lay the page out again each time)
function waveformPixels(clip){
  try{return Math.max(1,Number(clip.duration)/timelineSpan()*timelineWidth());}catch{return 200;}
}
function waveformBuckets(peaks,limit){
  if(peaks.length<=limit)return peaks;
  const out=[],step=peaks.length/limit;
  for(let i=0;i<limit;i++){
    let low=0,high=0;
    for(let j=Math.floor(i*step),end=Math.min(peaks.length,Math.floor((i+1)*step)||1);j<end;j++){const p=peaks[j];if(p[0]<low)low=p[0];if(p[1]>high)high=p[1];}
    out.push([low,high]);
  }
  return out;
}
function drawAudioWaveform(button,clip){
  if(!clip.asset_id)return;
  const url=audioWaveformUrl(clip);
  button.dataset.waveformSource=url;
  // a failed request is forgotten, so the next drawing asks again
  if(!waveformRequests.has(url))waveformRequests.set(url,fetch(url).then(r=>{if(!r.ok)throw new Error('Waveform unavailable');return r.json();}).catch(error=>{waveformRequests.delete(url);throw error;}));
  waveformRequests.get(url).then(data=>{
    if(!button.isConnected || button.dataset.waveformSource!==url || !data.peaks?.length)return;
    const first=Math.max(0,Math.floor(Number(clip.trim_start || 0)/data.duration*data.peaks.length)),last=Math.min(data.peaks.length,Math.ceil((Number(clip.trim_start || 0)+Number(clip.duration))/data.duration*data.peaks.length));
    // as many points as the clip has pixels (two a pixel, the loudest of each bucket kept): every waveform had all its
    // file's peaks, 325 sounds of Andromeda drew 4.8 million points and each zoom step and scroll painted them again
    // (user, 25 November 2026: «ще підвисає… ще швидше»); the next redraw after a zoom draws them for the new width
    // the waveform shows the sound as it is in its file, whatever its volume: music at 6% and effects at 7% drew a flat
    // line (user, 25 November 2026: «щоб музика… і SFX… не були такою тонкою лінією… візуально… як оригінальний звук»);
    // the volume itself is still the number beside the row
    const gain=1;
    let peaks=waveformBuckets(data.peaks.slice(first,last),Math.max(16,Math.min(4000,Math.ceil(waveformPixels(clip)*2))));if(!peaks.length)return;
    // each waveform reaches the row's height at its own loudest moment: effects are levelled far under full scale
    const loudest=Math.max(...peaks.map(p=>Math.max(Math.abs(p[0]),Math.abs(p[1])))),fit=loudest>1e-4?Math.min(12,.95/loudest):1;
    if(fit>1)peaks=peaks.map(p=>[p[0]*fit,p[1]*fit]);
    const upper=peaks.map((p,i)=>`${i/(Math.max(1,peaks.length-1))*1000},${20-Math.min(1,Math.max(0,p[1]*gain))*18}`);
    const lower=peaks.map((p,i)=>`${i/(Math.max(1,peaks.length-1))*1000},${20-Math.max(-1,Math.min(0,p[0]*gain))*18}`).reverse();
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('audio-waveform');svg.setAttribute('viewBox','0 0 1000 40');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M'+upper.join('L')+'L'+lower.join('L')+'Z');svg.append(path);button.querySelector('.audio-waveform')?.remove();button.prepend(svg);
  }).catch(()=>{button.title=(button.title || '')+' · Хвильова форма недоступна';});
}
