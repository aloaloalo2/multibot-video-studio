const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../project-next-action.js'),'utf8');
const c=vm.createContext({});vm.runInContext(source,c);
const decide=changes=>c.projectNextAction({script:'Full script.',hasScriptField:true,hasVoice:true,narrationEnabled:true,...changes});
test('the main path advances from hook through narration, video and export',()=>{
  assert.equal(decide({hooksPending:true,hasHooks:true}).kind,'hook');
  assert.equal(decide({}).kind,'narrate');
  assert.equal(decide({readyVoice:true,createEnabled:true}).kind,'create');
  assert.equal(decide({hasFrames:true,framesEnabled:true}).kind,'frames');
  assert.equal(decide({canExport:true}).kind,'export');
});
test('missing channel voice gives a concrete reason and settings destination',()=>{
  const value=decide({hasVoice:false});assert.equal(value.disabled,true);assert.equal(value.settings,'voice');assert.match(value.reason,/голосу/);
});
test('voice profile read errors have their own recovery reason',()=>{
  const value=decide({voiceError:true,hasVoice:false});
  assert.equal(value.disabled,true);assert.match(value.reason,/Повторіть завантаження/);assert.doesNotMatch(value.reason,/Немає голосу/);
});
test('a voice file remains usable without a configured channel voice',()=>{
  assert.equal(decide({hasVoice:false,fileMode:true}).kind,'file');
  const value=decide({hasVoice:false,fileMode:true,hasFile:true,uploadEnabled:true});assert.equal(value.kind,'upload');assert.equal(value.disabled,false);
});
test('busy stages expose no second production start',()=>{
  for(const key of ['writing','narrating','analyzing','planning','producing']){
    const value=decide({[key]:true,canExport:true});assert.equal(value.kind,'wait');assert.equal(value.disabled,true);
  }
});
test('local edits take precedence over an older ready voice and complete frames',()=>{
  assert.equal(decide({pendingScript:true,readyVoice:true,hasFrames:true,canExport:true}).kind,'narrate');
  assert.equal(decide({pendingScript:true,readyVoice:true,hasFrames:true,canExport:true,hasScriptField:false}).kind,'edit');
});
test('an old finished timeline cannot export before pending working text is loaded',()=>{
  const value=decide({draftLoading:true,canExport:true,hasScriptField:false});assert.equal(value.kind,'wait');assert.equal(value.disabled,true);
  const failure=decide({draftReadError:'Студія не відповідає',canExport:true,hasScriptField:false});assert.equal(failure.kind,'save');assert.equal(failure.reason,'Студія не відповідає');
});
test('a durable-draft conflict has an explicit recovery action',()=>{
  const value=decide({draftConflict:true});assert.equal(value.kind,'save');assert.equal(value.disabled,false);assert.match(value.reason,/історії/);
});
test('direct montage exports existing visuals without forcing narration',()=>{
  const value=decide({direct:true,hasPictures:true,canExport:true,script:'',hasVoice:false});assert.equal(value.kind,'export');assert.equal(value.disabled,false);
  assert.equal(decide({direct:true,script:'',hasVoice:false}).kind,'media');
});
test('direct voice import keeps the recognition-only workflow',()=>{
  assert.equal(decide({direct:true,readyVoice:true,createEnabled:true}).label,'Розпізнати аудіо');
  assert.equal(decide({direct:true,fileMode:true,hasFile:true,uploadEnabled:true}).label,'Розпізнати аудіо');
});
test('incomplete or paused production cannot masquerade as a finished export',()=>{
  assert.equal(decide({hasFrames:true,resume:true,framesEnabled:true}).label,'Продовжити створення ролика');
  const value=decide({hasFrames:true,allFrames:true,canExport:false,productionReason:'Перевірте таймінги'});
  assert.equal(value.disabled,true);assert.equal(value.reason,'Перевірте таймінги');
});
test('metadata and director recovery use their own explicit steps',()=>{
  assert.equal(decide({metadataPending:true}).kind,'metadata');
  assert.equal(decide({directionRecovery:true}).kind,'direction');
  assert.equal(decide({directionRecovery:true,pendingScript:true}).kind,'narrate');
});

test('choosing a narration file keeps its local Create video button visible',()=>{
  const marks=new Set(),local={classList:{add:k=>marks.add(k),remove:k=>marks.delete(k)}};
  const elements={'project-next-step':{},'project-next-action':{},'project-next-reason':{},'project-next-settings':{dataset:{}},'export-open':{}};
  const context={model:{script:'Saved script',fileMode:true,hasFile:true,uploadEnabled:true},root:{classList:{contains:()=>true}},targets:{upload:local}};
  const block=source.slice(source.indexOf('function updateProjectNextAction()'),source.indexOf('function focusWorkflowScript('));
  const testContext=vm.createContext({projectNextContext:()=>context,projectNextAction:c.projectNextAction,state:{view:'editor'},$:id=>elements[id],esc:String,projectNextIcons:{create:''},delegatedWorkflowTarget:null,projectNextBusy:false});
  vm.runInContext(block,testContext);testContext.updateProjectNextAction();
  assert.equal(elements['project-next-action'].disabled,false);
  assert.match(elements['project-next-action'].innerHTML,/Створити відео/);
  assert.equal(marks.has('workflow-action-target'),false);
});

test('a ready provider quote retains the local narration action and header dispatch',async()=>{
  const marks=new Set();let starts=0;
  const local={disabled:false,classList:{add:k=>marks.add(k),remove:k=>marks.delete(k)},click:()=>starts++};
  const elements={'project-next-step':{},'project-next-action':{},'project-next-reason':{},'project-next-settings':{dataset:{}},'export-open':{}};
  const context={model:{script:'Saved Fish script',hasScriptField:true,hasVoice:true,narrationEnabled:true},root:{classList:{contains:()=>true}},targets:{narrate:local}};
  marks.add('workflow-action-target');
  const block=source.slice(source.indexOf('function updateProjectNextAction()'),source.indexOf("if(typeof document!=="));
  const testContext=vm.createContext({projectNextContext:()=>context,projectNextAction:c.projectNextAction,state:{view:'editor'},$:id=>elements[id],esc:String,projectNextIcons:{narrate:''},delegatedWorkflowTarget:local,projectNextBusy:false});
  vm.runInContext(block,testContext);testContext.updateProjectNextAction();
  assert.equal(marks.has('workflow-action-target'),false);
  assert.equal(elements['project-next-action'].disabled,false);
  assert.match(elements['project-next-action'].innerHTML,/Озвучити/);
  await testContext.runProjectNextAction();assert.equal(starts,1);
  context.model.narrationEnabled=false;local.disabled=true;
  await testContext.runProjectNextAction();assert.equal(starts,1);
});
