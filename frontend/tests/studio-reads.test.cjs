const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../studio-reads.js'),'utf8');
function fixture(){let now=1000;const context=vm.createContext({Date:{now:()=>now}});vm.runInContext(source,context);return {c:context,advance:()=>now+=1000};}
const endpoint='/api/projects/'+'a'.repeat(24)+'/thumbnail?compact=1';
test('overlapping status reads and the settings editors share one request with independent results',async()=>{
  for(const key of [endpoint,'/api/settings']){
    const {c}=fixture();let finish,calls=0;const request=()=>{calls++;return new Promise(resolve=>finish=resolve);};
    const one=c.sharedStudioRead(key,request),two=c.sharedStudioRead(key,request);await Promise.resolve();assert.equal(calls,1);
    finish({job:{status:'running'}});const a=await one,b=await two;a.job.status='changed by consumer';assert.equal(b.job.status,'running');
    await c.sharedStudioRead(key,request);assert.equal(calls,1);
  }
});
test('mutations invalidate their project and an older response cannot repopulate that cache',async()=>{
  const {c}=fixture();let finish;const old=c.sharedStudioRead(endpoint,()=>new Promise(resolve=>finish=resolve));await Promise.resolve();
  c.invalidateStudioReads('/api/projects/'+'a'.repeat(24)+'/thumbnail');
  assert.equal((await c.sharedStudioRead(endpoint,async()=>({job:{status:'running'}}))).job.status,'running');
  finish({job:{status:'done'}});await old;
  assert.equal((await c.sharedStudioRead(endpoint,()=>{throw Error('cache lost');})).job.status,'running');
});
test('failures are retryable and elapsed status data is refreshed',async()=>{
  const {c,advance}=fixture();await assert.rejects(c.sharedStudioRead(endpoint,async()=>{throw Error('offline');}),/offline/);
  await c.sharedStudioRead(endpoint,async()=>({stage:1}));advance();assert.equal((await c.sharedStudioRead(endpoint,async()=>({stage:2}))).stage,2);
});
test('credentials, author drafts and mutations stay outside the status pool',async()=>{
  const {c}=fixture();for(const value of ['/api/service-keys','/api/projects/'+'a'.repeat(24)+'/script-draft','/api/settings/youtube-root/pick'])assert.equal(c.pooledStudioPath(value),false);
});
