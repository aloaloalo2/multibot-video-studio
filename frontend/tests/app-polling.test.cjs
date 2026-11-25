const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');

test('a hidden tab asks for the export progress at most every 5 s, a visible one as before',()=>{
  const line=source.match(/^function scheduleJobPoll\(.*$/m)[0],delays=[];
  const document={hidden:false},state={poll:null};
  const context=vm.createContext({document,state,clearTimeout(){},setTimeout:(fn,delay)=>{delays.push(delay);return 1;},pollJob(){}});
  vm.runInContext(line,context);
  context.scheduleJobPoll();context.scheduleJobPoll(0);
  document.hidden=true;context.scheduleJobPoll();context.scheduleJobPoll(15000);context.scheduleJobPoll(0);
  assert.deepEqual(delays,[1500,0,5000,15000,0]);
});

test('the open episode reads nothing while hidden and asks for the logo every third tick',()=>{
  const from=source.indexOf('  let exportWatchBusy=false'),to=source.indexOf('  return true;\n}',from);
  const block=source.slice(from,to);
  assert.match(block,/document\.hidden/);
  assert.match(block,/branding=\+\+exportWatchTicks%3===0/);
  assert.match(block,/if\(!branding\)return;/);
  assert.match(source,/if\(state\.project&&state\.exportWatch\)state\.exportWatchTick\?\.\(true\)/);
});

test('an open episode does not redraw the hidden overview cards',()=>{
  const body=source.slice(source.indexOf('function renderProject() {'),source.indexOf('\n}\n',source.indexOf('function renderProject() {')));
  assert.match(body,/if\(!state\.project\)renderOverview\(\);/);
  assert.doesNotMatch(body.replace('if(!state.project)renderOverview();',''),/renderOverview\(\)/);
});

test('the dead publishing-task text is gone',()=>{
  assert.doesNotMatch(source,/function youtubeSessionTask\(/);
});
