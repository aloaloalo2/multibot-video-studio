const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');
const fn=source.slice(source.indexOf('async function openExport()'),source.indexOf('function revealTimelineTime('));
function setup(fail=false){
  const calls=[],button={},render={isConnected:true},state={project:{id:'p',production:{export_ready:true}}};
  let submit;
  const context=vm.createContext({state,api:async(url,method)=>{
    if(url.endsWith('/export/active'))return {};
    if(url==='/api/health')return {export_queue:true};
    if(method==='POST'){if(fail)throw Error('Export refused');return {job:{id:'j',project_id:'p',status:'queued'}};}
    throw Error(url);
  },updateExportLock:()=>{},exportIsActive:()=>false,visualGaps:()=>[],exportQualityHtml:()=>'',exportSpinner:'spinner',
  modal:(title,body,actions)=>{calls.push('modal');submit=actions.at(-1).run;},
  closeModal:()=>calls.push('close'),showProjectList:()=>calls.push('overview'),pollJob:()=>calls.push('poll'),
  status:()=>calls.push('error'),document:{querySelector:()=>null,querySelectorAll:()=>[]},
  $:id=>id==='modal-actions'?{querySelector:()=>button}:render});
  vm.runInContext(fn,context);
  return {calls,state,button,open:()=>vm.runInContext('openExport()',context),submit:()=>submit()};
}
test('queued export closes confirmation and returns to the channel overview without opening progress',async()=>{
  const h=setup();await h.open();await h.submit();
  assert.deepEqual(h.calls,['modal','close','overview']);assert.equal(h.state.job.id,'j');
});
test('export submission failure keeps confirmation available for retry',async()=>{
  const h=setup(true);await h.open();await h.submit();
  assert.deepEqual(h.calls,['modal','error']);assert.equal(h.button.disabled,false);
});
test('a late export response does not pull the author out of a different project',async()=>{
  const h=setup();await h.open();const pending=h.submit();h.state.project={id:'other'};await pending;
  assert.deepEqual(h.calls,['modal']);assert.equal(h.state.job,undefined);
});
