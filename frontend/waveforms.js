const waveformRequests=new Map();
function drawAudioWaveform(button,clip){
  if(!clip.asset_id)return;
  const url=`/api/projects/${state.project.id}/assets/${clip.asset_id}/waveform`;
  if(!waveformRequests.has(url))waveformRequests.set(url,fetch(url).then(r=>{if(!r.ok)throw new Error('Waveform unavailable');return r.json();}));
  waveformRequests.get(url).then(data=>{
    if(!button.isConnected || !data.peaks?.length)return;
    const first=Math.max(0,Math.floor(Number(clip.trim_start || 0)/data.duration*data.peaks.length)),last=Math.min(data.peaks.length,Math.ceil((Number(clip.trim_start || 0)+Number(clip.duration))/data.duration*data.peaks.length));
    const peaks=data.peaks.slice(first,last),gain=Number(clip.volume ?? 1);if(!peaks.length)return;
    const upper=peaks.map((p,i)=>`${i/(Math.max(1,peaks.length-1))*1000},${20-Math.min(1,Math.max(0,p[1]*gain))*18}`);
    const lower=peaks.map((p,i)=>`${i/(Math.max(1,peaks.length-1))*1000},${20-Math.max(-1,Math.min(0,p[0]*gain))*18}`).reverse();
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('audio-waveform');svg.setAttribute('viewBox','0 0 1000 40');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M'+upper.join('L')+'L'+lower.join('L')+'Z');svg.append(path);button.querySelector('.audio-waveform')?.remove();button.prepend(svg);
  }).catch(()=>{button.title=(button.title || '')+' · Хвильова форма недоступна';});
}
