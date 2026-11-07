const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function load(api,running=()=>false){
  const context=vm.createContext({api,langRunning:running,esc:value=>String(value)});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../language-scripts.js'),'utf8'),context);
  return context;
}

test('an empty script card starts translation directly once and shows pending progress',async()=>{
  const context=load(()=>assert.fail('No direct API call expected'));
  let finish;const pending=new Promise(resolve=>finish=resolve),calls=[];
  context.state={project:{id:'p'}};context.langData={items:[{code:'uk',name:'Українська',text:''}]};
  context.langStart=async(...args)=>{calls.push(args);await pending;return true;};
  context.langOpenScript=()=>assert.fail('Empty cards must not open an editor');context.langPaintScriptJobs=()=>{};
  const label={},progress={hidden:true,removeAttribute(){}},attributes={};
  const button={disabled:false,setAttribute:(k,v)=>attributes[k]=v,removeAttribute:k=>delete attributes[k],querySelector:selector=>selector==='progress'?progress:label};
  const run=context.langActivateScript('p','uk',button);
  await context.langActivateScript('p','uk',button);
  assert.deepEqual(calls,[['p','translate','uk']]);assert.equal(button.disabled,true);assert.equal(progress.hidden,false);
  assert.match(label.textContent,/Запускаємо переклад/);assert.equal(context.langScriptStatus(context.langData.items[0]).kind,'working');
  finish();await run;assert.equal(button.disabled,false);assert.equal(attributes['aria-busy'],undefined);
});

test('existing scripts and active translations still open their details without starting paid work',async()=>{
  for(const item of [{code:'uk',text:'Готовий текст'},{code:'uk',text:'',translation_resumable:true}]){
    const context=load(()=>assert.fail('Must not start API requests'));context.state={project:{id:'p'}};context.langData={items:[item]};
    const opened=[];context.langOpenScript=(...args)=>opened.push(args);context.langStart=()=>assert.fail('Must preserve saved translations');
    await context.langActivateScript('p','uk',{});assert.deepEqual(opened,[['p','uk']]);
  }
});

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

test('disputed phrase supervision is labelled as the linguist with the actual model name',()=>{
  const context=load(()=>assert.fail('Rendering progress must not call the API'));
  const status=context.langTranslationProgress({status:'running',progress:95,
    translation_review:{phase:'linguist',total:125,batch_size:1,waiting:true,model_name:'DeepSeek',request_started_at:100}},105);
  assert.equal(status.label,'Лінгвіст');assert.match(status.detail,/DeepSeek/);assert.match(status.detail,/1 фраз/);
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


test('wrong-language phrase warning identifies exact lines and permits ordinary names',()=>{
  const context=load(()=>assert.fail('Local warning must not call API'));
  const bad={language_check:{state:'blocked',issues:[{index:16,detected:'ru'},{index:23,detected:'pl'}]}};
  assert.match(context.langScriptLanguageWarning(bad),/17, 24/);
  assert.match(context.langScriptLanguageWarning(bad),/Озвучення заблоковано/);
  assert.equal(context.langScriptLanguageWarning({language_check:{state:'ok'}}),'');
});


test('card percentage uses the same number-aware letter basis as its count',()=>{
  const context=load(()=>assert.fail('Local metric needs no request'));
  const result=context.langScriptDifference({translation_length:{number_comparison:{available:true,source_chars:41477,translated_chars:43254,difference_percent:4.28},script_comparison:{tolerance_percent:7}}});
  assert.equal(result.label,'+4,28%');assert.equal(result.over,false);assert.match(result.title,/43.*254.*41.*477/);
  assert.equal(context.langScriptDifference({}),null);
  const markup=context.langScriptCharacters({display_chars:43254,translation_length:{number_comparison:{available:true,source_chars:41453,translated_chars:43254,difference_percent:4.34}}});
  assert.match(markup,/43,3K.*\(\+4,34%\)/);
  assert.doesNotMatch(markup,/<small>/);
});
