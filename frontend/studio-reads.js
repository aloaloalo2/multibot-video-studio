// Coalesce read-only status/settings requests across views; mutations never enter this pool.
const studioReads=new Map();
const studioReadTTL=450,studioReadLimit=128;
function pooledStudioPath(path){return path==='/api/settings'||path==='/api/studio/status'||/^\/api\/(?:projects\/[0-9a-f]{24}\/(?:analysis|thumbnail|narration|director|create-video|performance)|channels\/[0-9a-f]{16}\/voice-lab)(?:\?|$)/.test(path);}
function invalidateStudioReads(path){
  const project=path.match(/^\/api\/projects\/([0-9a-f]{24})(?:\/|$)/),channel=path.match(/^\/api\/channels\/([0-9a-f]{16})(?:\/|$)/);
  for(const key of studioReads.keys())if(path==='/api/settings'||key==='/api/studio/status'||project&&key.startsWith('/api/projects/'+project[1]+'/')||channel&&key.startsWith('/api/channels/'+channel[1]+'/'))studioReads.delete(key);
}
function sharedStudioRead(path,request){
  if(!pooledStudioPath(path))return request();
  const clone=value=>typeof structuredClone==='function'?structuredClone(value):JSON.parse(JSON.stringify(value));
  const previous=studioReads.get(path),now=Date.now();
  if(previous?.pending)return previous.pending.then(clone);
  if(previous&&now-previous.saved<studioReadTTL)return Promise.resolve(clone(previous.value));
  const entry={saved:0};studioReads.set(path,entry);
  while(studioReads.size>studioReadLimit)studioReads.delete(studioReads.keys().next().value);
  entry.pending=Promise.resolve().then(request).then(value=>{if(studioReads.get(path)===entry){entry.value=value;entry.saved=Date.now();}return value;}).catch(error=>{if(studioReads.get(path)===entry)studioReads.delete(path);throw error;}).finally(()=>{entry.pending=null;});
  return entry.pending.then(clone);
}
