const waveformRequests=new Map(),waveformData=new Map(),waveformPaths=new Map();
const WAVEFORM_PATHS=4000;   // drawn outlines kept (a long film has a few hundred sounds, each at a zoom or two)
function audioWaveformUrl(clip){
  const dubbed=typeof dubbedVoiceUrl==='function'?dubbedVoiceUrl(clip):null;
  return dubbed?dubbed.replace('/file/voice','/waveform'):`/api/projects/${state.project.id}/assets/${clip.asset_id}/waveform`;
}
// the clip's width on the timeline, from its length (measuring each of 325 clips would lay the page out again each time)
function waveformPixels(clip){
  try{return Math.max(1,Number(clip.duration)/timelineSpan()*timelineWidth());}catch{return 200;}
}
// two points a pixel, rounded up to a power of two: a zoom step that changes a width a little reuses the outline drawn
// for it, and a waveform never has fewer points than half its pixels
function waveformPoints(clip){
  const wanted=Math.max(16,Math.min(4096,Math.ceil(waveformPixels(clip)*2)));
  return 2**Math.ceil(Math.log2(wanted));
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
// The outline of a clip's part of its file, the same for every redraw of one clip at one width: 325 sounds of
// Andromeda built theirs again on every redraw of the timeline, about 250 ms after each click (25 November 2026).
function waveformPath(data,clip,points){
  const trim=Number(clip.trim_start || 0),length=Number(clip.duration);
  const first=Math.max(0,Math.floor(trim/data.duration*data.peaks.length)),last=Math.min(data.peaks.length,Math.ceil((trim+length)/data.duration*data.peaks.length));
  // as many points as the clip has pixels (two a pixel, the loudest of each bucket kept): every waveform had all its
  // file's peaks, 325 sounds of Andromeda drew 4.8 million points and each zoom step and scroll painted them again
  // (user, 25 November 2026: «ще підвисає… ще швидше»); the next redraw after a zoom draws them for the new width
  // the waveform shows the sound as it is in its file, whatever its volume: music at 6% and effects at 7% drew a flat
  // line (user, 25 November 2026: «щоб музика… і SFX… не були такою тонкою лінією… візуально… як оригінальний звук»);
  // the volume itself is still the number beside the row
  const peaks=waveformBuckets(first===0&&last===data.peaks.length?data.peaks:data.peaks.slice(first,last),points);if(!peaks.length)return '';
  // each waveform reaches the row's height at its own loudest moment: effects are levelled far under full scale
  let loudest=0;for(const p of peaks){const v=Math.max(Math.abs(p[0]),Math.abs(p[1]));if(v>loudest)loudest=v;}
  const fit=loudest>1e-4?Math.max(1,Math.min(12,.95/loudest)):1,last1=Math.max(1,peaks.length-1);
  const upper=new Array(peaks.length),lower=new Array(peaks.length);
  for(let i=0;i<peaks.length;i++){
    const x=i/last1*1000;
    upper[i]=`${x},${20-Math.min(1,Math.max(0,peaks[i][1]*fit))*18}`;
    lower[peaks.length-1-i]=`${x},${20-Math.max(-1,Math.min(0,peaks[i][0]*fit))*18}`;
  }
  return 'M'+upper.join('L')+'L'+lower.join('L')+'Z';
}
let waveformTemplate=null,waveformPass=0,waveformPasses=0;const waveformUse=new WeakMap();
// The drawn outline of a clip is kept and moved into the clip's block of the next redraw (the old block is gone by
// then), so a redraw neither builds nor parses it again; a second clip of the same sound shown at once gets a copy.
function placeWaveform(button,url,data,clip){
  if(!data.peaks?.length)return;
  const points=waveformPoints(clip),key=`${url}|${Number(clip.trim_start || 0)}|${Number(clip.duration)}|${points}`;
  let svg=waveformPaths.get(key);
  if(svg===undefined){
    const d=waveformPath(data,clip,points);svg=null;
    if(d){
      if(!waveformTemplate){
        waveformTemplate=document.createElementNS('http://www.w3.org/2000/svg','svg');waveformTemplate.classList.add('audio-waveform');
        waveformTemplate.setAttribute('viewBox','0 0 1000 40');waveformTemplate.setAttribute('preserveAspectRatio','none');waveformTemplate.setAttribute('aria-hidden','true');
        waveformTemplate.append(document.createElementNS('http://www.w3.org/2000/svg','path'));
      }
      svg=waveformTemplate.cloneNode(true);svg.firstChild.setAttribute('d',d);
    }
    if(waveformPaths.size>=WAVEFORM_PATHS)waveformPaths.delete(waveformPaths.keys().next().value);
    waveformPaths.set(key,svg);
  }
  if(!svg)return;
  const old=button.querySelector('.audio-waveform');
  if(old===svg)return;
  // blocks are drawn before they join the page, so «already placed in this redraw» is told by the pass
  if(!waveformPass){waveformPass=++waveformPasses;queueMicrotask(()=>{waveformPass=0;});}
  const busy=svg.isConnected||waveformUse.get(svg)===waveformPass;
  if(busy)svg=svg.cloneNode(true);else waveformUse.set(svg,waveformPass);
  old?.remove();button.prepend(svg);
}
function drawAudioWaveform(button,clip){
  if(!clip.asset_id)return;
  const url=audioWaveformUrl(clip);
  button.dataset.waveformSource=url;
  // a file read once is drawn at once, inside the same redraw: no second pass over hundreds of sounds after it
  const ready=waveformData.get(url);
  if(ready){placeWaveform(button,url,ready,clip);return;}
  // a failed request is forgotten, so the next drawing asks again
  if(!waveformRequests.has(url))waveformRequests.set(url,fetch(url).then(r=>{if(!r.ok)throw new Error('Waveform unavailable');return r.json();}).then(data=>{waveformData.set(url,data);return data;}).catch(error=>{waveformRequests.delete(url);throw error;}));
  waveformRequests.get(url).then(data=>{
    if(!button.isConnected || button.dataset.waveformSource!==url)return;
    placeWaveform(button,url,data,clip);
  }).catch(()=>{button.title=(button.title || '')+' · Хвильова форма недоступна';});
}
