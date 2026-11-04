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

test('translation cost is rounded to three dollars decimals and unknown cost stays hidden',()=>{
  const context=load(()=>assert.fail('Display must not call the API'));
  assert.equal(context.langScriptCost({translate_cost:.02845}),'$0.028');
  assert.equal(context.langScriptCost({translate_cost:.1196}),'$0.120');
  assert.equal(context.langScriptCost({translate_cost:0}),'$0.000');
  for(const translate_cost of [undefined,null,-1,NaN,Infinity,'0.05']){
    assert.equal(context.langScriptCost({translate_cost}),'');
  }
});

test('script size uses compact K formatting without changing exact counts',()=>{
  const context=load(()=>assert.fail('A count must not start a request'));
  assert.equal(context.langShortCharacters(5600),'5,6K');
  assert.equal(context.langShortCharacters(2300),'2,3K');
  assert.equal(context.langShortCharacters(2002),'2K');
  assert.equal(context.langShortCharacters(999),'999');
  assert.equal(context.langShortCharacters(1000),'1K');
  assert.equal(context.langScriptCharacters({display_chars:0}),'');
});

test('review shows measured total progress and provider wait without a fake completion percentage',()=>{
  const context=load(()=>assert.fail('Display must not call the API'));
  const job={status:'running',progress:95,stage:'Legacy stage',
    translation_review:{phase:'length',total:341,batch_size:20,waiting:true,request_started_at:100},
    translation_length:{phrase_comparison:{available:true,total:341,outside_count:40}}};
  const status=context.langTranslationProgress(job,175);
  assert.equal(status.indeterminate,true);
  assert.match(status.detail,/301 з 341/);
  assert.match(status.detail,/20 фраз/);
  assert.match(status.detail,/MiniMax.*1:15/);
  assert.equal(status.compact,'301/341');
  assert.equal(status.label,'Узгодження');
  const audit=context.langTranslationProgress({...job,translation_review:{...job.translation_review,phase:'audit',audited:320}},175);
  assert.equal(audit.compact,status.compact);
  assert.equal(audit.label,'Перевірка');
  const legacy=context.langTranslationProgress({status:'running',progress:95,
    stage:'Уточнюємо переклад: готово 0 з 20 фраз'});
  assert.equal(legacy.indeterminate,true);
  assert.doesNotMatch(legacy.detail,/0 з 20/);
  assert.match(legacy.detail,/20 фраз/);
  assert.equal(context.langTranslationProgress({status:'running',progress:45,stage:'Перекладаємо'}).indeterminate,false);
});
