const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
function fixture(){
  const node=()=>({children:[],hidden:false,isConnected:true,dataset:{},attributes:{},events:{},classList:{add(){},remove(){}},replaceChildren(){this.children=[]},append(child){this.children.push(child)},addEventListener(name,fn){this.events[name]=fn},setAttribute(k,v){this.attributes[k]=v},removeAttribute(k){delete this.attributes[k]},get textContent(){return this.text||this.children.map(n=>n.textContent).join('')},set textContent(v){this.text=v},querySelector(){return null},querySelectorAll(){return []}});
  const elements=Object.fromEntries(['modal-body','modal-title','modal-actions','modal-backdrop','export-open','render-state'].map(id=>[id,node()]));
  elements['export-open'].querySelector=()=>({cloneNode:node});
  elements['modal-actions'].querySelector=()=>elements['modal-actions'].children[0];
  const c=vm.createContext({state:{},$:id=>elements[id],stopModalMedia(){},document:{createElement:node,activeElement:null},HTMLElement:class{},HTMLInputElement:class{},setTimeout});
  vm.runInContext(source.slice(source.indexOf('const modalActionPaths='),source.indexOf('function stopModalMedia(')),c);
  return {c,elements};
}
test('informational dialogs have no empty footer, and the next dialog still exposes its real action',()=>{
  const {c,elements}=fixture();c.modal('Info','<p>Message</p>');
  assert.equal(elements['modal-actions'].hidden,true);
  c.modal('Save','<p>Form</p>',[{label:'Зберегти',primary:true,run(){}}]);
  assert.equal(elements['modal-actions'].hidden,false);
  assert.equal(elements['modal-actions'].children.length,1);
  assert.equal(elements['modal-actions'].children[0].textContent,'Зберегти');
});
test('replacing a modal disposes the prior editor once and releases its retained callback',()=>{
  const {c,elements}=fixture();let disposals=0;elements['modal-body'].channelSettingsCleanup=()=>disposals++;
  c.modal('First','');c.modal('Next','');
  assert.equal(disposals,1);assert.equal(elements['modal-body'].channelSettingsCleanup,undefined);
});
test('export progress retains cancellation of the job without a duplicate close action',()=>{
  const c=vm.createContext({state:{job:{status:'running'}}});
  vm.runInContext(source.slice(source.indexOf('function exportActions('),source.indexOf('// The film',source.indexOf('function exportActions('))),c);
  assert.deepEqual(Array.from(c.exportActions(),item=>item.label),['Скасувати експорт']);
  c.state.job.status='cancelling';assert.equal(c.exportActions().length,0);
});

test('a pending modal action cannot be submitted twice and exposes busy state',async()=>{
  const {c,elements}=fixture();let calls=0,finish;
  c.modal('Save','',[{label:'Зберегти',primary:true,run:()=>{calls++;return new Promise(resolve=>finish=resolve)}}]);
  const button=elements['modal-actions'].children[0],first=button.events.click({});
  await button.events.click({});assert.equal(calls,1);assert.equal(button.disabled,true);assert.equal(button.attributes['aria-busy'],'true');
  finish();await first;assert.equal(button.disabled,false);assert.equal(button.attributes['aria-busy'],undefined);
});
test('a modal action retains its workflow validation after its request returns',async()=>{
  const {c,elements}=fixture();let allowed=false;
  c.modal('Analyze','',[{label:'Обробити файл',enabled:()=>allowed,run:async()=>{}}]);
  const button=elements['modal-actions'].children[0];await button.events.click({});assert.equal(button.disabled,true);
  allowed=true;button.disabled=false;await button.events.click({});assert.equal(button.disabled,false);
});

test('an unexpected action error stays visible and releases its button for retry',async()=>{
  const {c,elements}=fixture();const messages=[];c.status=(...args)=>messages.push(args);
  c.modal('Save','',[{label:'Зберегти',primary:true,run:async()=>{throw Error('Storage unavailable')}}]);
  const button=elements['modal-actions'].children[0];await button.events.click({});
  assert.deepEqual(messages,[['Storage unavailable',true]]);
  assert.equal(button.disabled,false);assert.equal(button.attributes['aria-busy'],undefined);
});
test('Start export through the real modal wrapper submits once despite its busy button',async()=>{
  const {c,elements}=fixture();let posts=0,closed=0,overview=0,finish;
  Object.assign(c,{state:{project:{id:'p',production:{export_ready:true}}},api:async(url,method)=>{
    if(url.endsWith('/export/active'))return {};
    if(url==='/api/health')return {export_queue:true};
    if(method==='POST'){posts++;return new Promise(resolve=>finish=resolve);}
    throw Error(url);
  },updateExportLock(){},exportIsActive:()=>false,visualGaps:()=>[],exportQualityHtml:()=>'',exportSpinner:'spinner',
  closeModal:()=>closed++,showProjectList:()=>overview++,status(){}});
  c.document.querySelector=()=>null;c.document.querySelectorAll=()=>[];
  vm.runInContext(source.slice(source.indexOf('async function openExport()'),source.indexOf('function revealTimelineTime(')),c);
  await c.openExport();
  const button=elements['modal-actions'].children[0],pending=button.events.click({});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(posts,1);
  await button.events.click({});assert.equal(posts,1);
  finish({job:{id:'export-job',project_id:'p',status:'queued'}});await pending;
  assert.equal(c.state.job.id,'export-job');assert.equal(closed,1);assert.equal(overview,1);
});
test('Enter submits a single-field dialog, never a settings form or an already-handled key',()=>{
  const {c}=fixture();const input=vm.runInContext('new HTMLInputElement()',c);input.type='text';input.getClientRects=()=>[{}];
  const other={type:'number',getClientRects:()=>[{}]},button={};let fields=[input];
  const body={querySelectorAll:()=>fields},actions={querySelector:()=>button};
  const event={key:'Enter',target:input};
  assert.equal(c.modalSubmitTarget(event,body,actions),button);
  fields=[input,other];assert.equal(c.modalSubmitTarget(event,body,actions),null);
  fields=[input];assert.equal(c.modalSubmitTarget({...event,defaultPrevented:true},body,actions),null);
  assert.equal(c.modalSubmitTarget({...event,repeat:true},body,actions),null);
});
