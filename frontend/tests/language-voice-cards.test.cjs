const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

function runtime(){
  const confirmations=[],requests=[];
  const context=vm.createContext({
    $:()=>null,state:{project:{id:'project-a'},view:'langs'},
    document:{addEventListener(){},querySelectorAll(){return [];}},
    clearTimeout(){},setTimeout(){return 0;},
    langFlushScript:async()=>true,closeModal(){},esc:String,
    modal:(...args)=>confirmations.push(args),
    api:async(...args)=>{requests.push(args);return args[0].startsWith('/api/elevenlabs/balance')?{state:'ready',remaining_credits:23456}:{status:'ready',original:[],translated:[]};},
    clock:value=>String(value),console,
  });
  for(const file of ['languages.js','language-alignment.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),context);
  vm.runInContext(`langData={provider:'fishaudio',providers:[{id:'fishaudio',name:'Fish',engine:'fish'},{id:'elevenlabs',name:'ElevenLabs',engine:'turbo',unit:'credits'}],source:{voice:true},jobs:[],items:[
    {code:'uk',name:'Українська',provider:'elevenlabs',text:'Український текст',chars:50,prices:{elevenlabs:13},files:{},voice_estimates:{elevenlabs:{total:2,reused:1,generate:1}}},
    {code:'pl',name:'Polski',provider:'fishaudio',text:'Polski tekst',chars:100,prices:{fishaudio:0},files:{},voice_estimates:{fishaudio:{total:3,reused:3,generate:0}}}
  ]};`,context);
  return {context,confirmations,requests,run:code=>vm.runInContext(code,context)};
}

test('confirmation uses the clicked language provider, estimate and cache, without starting synthesis',async()=>{
  const env=runtime();await env.run("langConfirmVoice('project-a','uk')");
  assert.equal(env.confirmations.length,1);
  assert.match(env.confirmations[0][0],/Українська/);
  assert.match(env.confirmations[0][1],/ElevenLabs/);
  assert.match(env.confirmations[0][1],/13 кредитів/);
  assert.match(env.confirmations[0][1],/1 із 2/);
  assert.deepEqual(env.requests.map(call=>call[0]),['/api/elevenlabs/balance?refresh=1']);
  assert.match(env.confirmations[0][1],/lang-confirm-balance/);
});

test('confirmation paints cached balance immediately and refreshes only account balance',async()=>{
  const env=runtime();env.run("langBalance={state:'ready',remaining_credits:1000}");
  await env.run("langConfirmVoice('project-a','uk')");
  assert.match(env.confirmations[0][1],/Баланс ElevenLabs/);
  assert.match(env.confirmations[0][1],/1\s*000 кредитів/);
  await new Promise(setImmediate);
  assert.match(env.run('langBalanceMarkup()'),/23\s*456 кредитів/);
  env.run("langBalance={state:'stale',remaining_credits:0}");
  assert.match(env.run('langBalanceMarkup()'),/0 кредитів/);
  assert.match(env.run('langBalanceMarkup()'),/Останній відомий баланс/);
  env.run("langBalance={state:'unavailable'}");
  assert.match(env.run('langBalanceMarkup()'),/Недоступний/);
  assert.ok(env.requests.every(call=>call[0].startsWith('/api/elevenlabs/balance')));
});

test('narration confirmation uses the selected language tempo allowance',async()=>{
  const env=runtime();env.run("langData.tempo_percent=15;langData.items[0].tempo_percent=17");
  await env.run("langConfirmVoice('project-a','uk')");
  assert.match(env.confirmations[0][1],/до 17%/);
  await env.run("langConfirmVoice('project-a','pl')");
  assert.match(env.confirmations[1][1],/до 15%/);
});

test('cached-only confirmation stays free and unrelated busy languages do not lock it',async()=>{
  const env=runtime();env.run("langData.jobs=[{code:'uk',kind:'voice',status:'running'}]");
  await env.run("langConfirmVoice('project-a','pl')");
  assert.match(env.confirmations[0][1],/без платних запитів/);
  assert.match(env.confirmations[0][2][1].label,/безкоштовно/);
  await env.run("langConfirmVoice('project-a','uk')");
  assert.equal(env.confirmations.length,1);
  await env.run("langConfirmVoice('another-project','pl')");
  assert.equal(env.confirmations.length,1);
});

test('saved, stale, failed and working states follow the correct language',()=>{
  const env=runtime();
  env.run("Object.assign(langData.items[0],{files:{voice:true},voice:{provider:'elevenlabs',duration:12},saved_mix:{state:'saved'}})");
  assert.equal(env.run('langVoiceTileState(langData.items[0]).kind'),'ready');
  env.run("langData.items[0].voice_current=false");
  assert.equal(env.run('langVoiceTileState(langData.items[0]).kind'),'action');
  env.run("langData.jobs=[{code:'pl',kind:'voice',status:'failed',error:'failure'}]");
  assert.equal(env.run('langVoiceTileState(langData.items[0]).kind'),'action');
  assert.equal(env.run('langVoiceTileState(langData.items[1]).kind'),'attention');
  env.run("langData.jobs.push({code:'pl',kind:'voice',status:'running',progress:43})");
  assert.equal(env.run('langVoiceTileState(langData.items[1]).progress'),43);
});

test('alignment reads are shared by cards and modal within the same overview snapshot',async()=>{
  const env=runtime();
  await Promise.all([env.run("langAlignmentLoad('project-a',langData.items[0])"),env.run("langAlignmentLoad('project-a',langData.items[0])")]);
  assert.equal(env.requests.length,1);
  env.run('langData={...langData}');
  await env.run("langAlignmentLoad('project-a',langData.items[0])");
  assert.equal(env.requests.length,2);
});

test('all translated rows show number-normalized character differences',()=>{
  const env=runtime();
  const result=env.run("langAlignmentCharacters({text:'twenty three'},{available:true,source_chars:10,translated_chars:12,difference_percent:20},4)");
  assert.match(result.label,/12 літер \(\+20%\)/);
  const raw=env.run("langAlignmentCharacters({text:'twenty three'},{available:false},4)");
  assert.doesNotMatch(raw.label,/%/);
  assert.equal(raw.label,'Підрахунок недоступний');
  const original=env.run("langAlignmentCharacters({text:'On October 4, 2021, something like that happened to Facebook.'},{available:true,source_chars:44,translated_chars:40,difference_percent:-9.09},0)");
  assert.equal(original.label,'44 літер');
});

test('a completed voice with timing issues remains playable and clearly needs review',()=>{
  const env=runtime();
  env.run("Object.assign(langData.items[0],{files:{voice:true},voice:{provider:'elevenlabs',timing_status:'review',duration:13},saved_mix:{state:'saved'}})");
  const status=env.run('langVoiceTileState(langData.items[0])');
  assert.equal(status.kind,'ready');
  assert.equal(status.review,true);
  assert.match(status.label,/Перевірити синхронізацію/);
});

test('duration mismatch overrides an old saved checkmark in either direction',()=>{
  for(const [duration,label] of [[2400,'Тривалість перевищена'],[2200,'Тривалість закоротка']]){
    const env=runtime();
    env.context.audioDuration=duration;
    env.run("Object.assign(langData.items[0],{files:{voice:true},voice:{provider:'elevenlabs',duration:audioDuration,source_duration:2280},saved_mix:{state:'saved'}})");
    const status=env.run('langVoiceTileState(langData.items[0])');
    assert.equal(status.kind,'attention');assert.equal(status.durationIssue,true);assert.equal(status.label,label);
    assert.equal(env.run('langVoiceStatus(langData.items[0],langSpec(langData.items[0]))'),label);
    assert.equal(env.requests.length,0);
  }
  const env=runtime();
  env.run("Object.assign(langData.items[0],{files:{voice:true},voice:{provider:'elevenlabs',duration:2280.02,source_duration:2280},saved_mix:{state:'saved'}})");
  assert.equal(env.run('langVoiceTileState(langData.items[0]).kind'),'ready');
});

test('cancellation remains disabled through stale polls and is scoped to the project and run',async()=>{
  const env=runtime();
  env.run("langData.jobs=[{code:'uk',kind:'voice',slot:'uk|voice',started_at:100,status:'running'}];showLangJob=()=>{};");
  const button={disabled:false,textContent:'Скасувати'};env.context.cancelButton=button;
  await env.run("langCancel('project-a','uk|voice',cancelButton)");
  assert.equal(button.disabled,true);
  assert.match(env.run('langCancelButton(langData.jobs[0])'),/ disabled/);
  await env.run("langCancel('project-a','uk|voice',cancelButton)");
  assert.equal(env.requests.length,1);
  env.run('langData.jobs[0]={...langData.jobs[0]}');
  assert.equal(env.run('langStopping(langData.jobs[0])'),true);
  assert.equal(env.run("langStopping(langData.jobs[0],'project-b')"),false);
  env.run('langData.jobs[0].started_at=101');
  assert.equal(env.run('langStopping(langData.jobs[0])'),false);
  env.run('langData.jobs[0].cancel_requested=true');
  assert.match(env.run('langCancelButton(langData.jobs[0])'),/ disabled/);
});


test('translation label shows only the combined cost, regardless of contributing models',()=>{
  const env=runtime();
  const label=env.run("langTranslationInfo({translated_model:'minimax/minimax-m3.1-flash',translation_repair_model:'deepseek/model',translate_cost:.12345})");
  assert.equal(label,'Переклад · $0.123');
  assert.equal(env.run('langTranslationInfo({translate_cost:0})'),'Переклад · $0.000');
  assert.equal(env.run('langTranslationInfo({})'),'');
});


test('wrong-language text disables narration and never opens a paid confirmation',async()=>{
  const env=runtime();env.run("langData.items[0].language_check={state:'blocked',issues:[{index:16,detected:'ru'}]}");
  assert.equal(env.run('langVoiceTileState(langData.items[0]).blocked'),true);
  await env.run("langConfirmVoice('project-a','uk')");
  assert.equal(env.confirmations.length,0);assert.equal(env.requests.length,0);
});


test('a single wrong-language warning displays the actual phrase immediately',()=>{
  const env=runtime();
  const text=env.run(`langQualityNotice({state:'blocked',issues:[{index:136,detected:'ru',text:'Люди чувствовали вину.'}]})`);
  assert.match(text,/<details open>/);assert.match(text,/Фраза 137/);assert.match(text,/Люди чувствовали вину/);
});

test('only Unicode letters count in source, translated and alignment displays',()=>{
  const env=runtime();
  assert.equal(env.run(`langLetters("Hello 123, world! — 🙂")`),10);
  assert.equal(env.run(`langLetters("пʼять п’ять п'ять")`),12);
  assert.equal(env.run(`langLetters("¿Hola? ¡Sí!")`),6);
});


test('unfinished scripts keep narration inactive even with a saved narrator voice',async()=>{
  const env=runtime();env.run("langData.items[0].text='';langData.items[0].translation_resumable={available:true}");
  const status=env.run('langVoiceTileState(langData.items[0])');
  assert.equal(status.kind,'blocked');assert.equal(status.blocked,true);assert.match(status.label,/завершіть переклад/);
  await env.run("langConfirmVoice('project-a','uk')");
  assert.equal(env.requests.length,0);assert.equal(env.confirmations.length,0);
});
