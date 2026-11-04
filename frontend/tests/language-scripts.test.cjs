const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function load(api,running=()=>false){
  const context=vm.createContext({api,langRunning:running});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../language-scripts.js'),'utf8'),context);
  return context;
}

test('selected languages start independently, once, with no voice requests',async()=>{
  const calls=[],started=new Set();let release;
  const pending=new Promise(resolve=>release=resolve);
  const context=load(async(url,method,body)=>{
    calls.push({url,method,body});
    const code=url.split('/')[5];
    if(!url.endsWith('/translate'))return {items:[{code,text:''}]};
    started.add(code);if(started.size===2)release();
    await pending;
    return {job:{code,slot:code+'|voice',status:'running',kind:'translate'}};
  });
  const results=await Promise.race([
    context.langRequestTranslations('project-a',['uk','pl','uk']),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('Languages blocked each other')),500)),
  ]);
  assert.deepEqual([...started].sort(),['pl','uk']);
  assert.equal(calls.length,4);
  assert.equal(results.length,2);
  assert.ok(results.every(result=>result.job.kind==='translate'));
  assert.ok(calls.every(call=>call.url.includes('/project-a/')&&call.method==='POST'));
});

test('one failed start leaves the other job running without automatic retries',async()=>{
  const attempts={};
  const context=load(async url=>{
    attempts[url]=(attempts[url]||0)+1;
    const code=url.split('/')[5];
    if(url.endsWith('/uk/translate'))throw Error('Key limit reached');
    return url.endsWith('/translate')?{job:{code,status:'running'}}:{items:[{code,text:''}]};
  });
  const results=await context.langRequestTranslations('project-b',['uk','pl']);
  assert.equal(results.find(result=>result.code==='uk').error,'Key limit reached');
  assert.equal(results.find(result=>result.code==='pl').job.status,'running');
  assert.ok(Object.values(attempts).every(count=>count===1));
});

test('picker omits source, completed translations and busy languages, but permits unfinished ones',()=>{
  const context=load(()=>assert.fail('Selecting must not start a request'),code=>code==='fr');
  const data={source:{language:'en'},items:[{code:'pl',text:'Ready'},{code:'uk',text:''}],
    languages:['en','pl','uk','fr','es'].map(code=>({code}))};
  assert.deepEqual(Array.from(context.langScriptAvailable(data),item=>item.code),['uk','es']);
});
