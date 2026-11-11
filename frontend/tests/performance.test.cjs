const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../performance.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function fixture(){
  const requests=[],waiting=[],timers=new Set(),button={hidden:true,addEventListener(){}};
  const body={querySelector(){return panel;}};
  let panel;
  const context={
    state:{project:{id:'one'},navigation:1,modalGeneration:0},
    esc:value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
    $:id=>id==='project-performance'?button:body,
    modal(){body.channelSettingsCleanup?.();if(panel)panel.isConnected=false;context.state.modalGeneration++;panel={isConnected:true,innerHTML:'loading',querySelectorAll(){return [];}};},
    api(path,method){requests.push({path,method});const value=deferred();waiting.push(value);return value.promise;},
    setTimeout(callback){timers.add(callback);return callback;},clearTimeout(callback){timers.delete(callback);},
  };
  vm.createContext(context);vm.runInContext(source,context);
  return {context,body,button,requests,waiting,timers,panel:()=>panel};
}
function report(status='complete'){
  return {runs:[{id:'r',workflow:'script',status,elapsed_ms:2000,stages:{service:{ms:2000}},language:'ru'}],
    stages:{service:'Очікування сервісу'},workflows:{script:'Сценарій'},stage_totals_ms:{service:2000}};
}
test('completed local reports do not start polling or paid mutations',async()=>{
  const f=fixture();f.context.openPerformance();f.waiting[0].resolve(report());await settle();
  assert.equal(f.requests.length,1);assert.equal(f.requests[0].method,undefined);
  assert.equal(f.requests[0].path,'/api/projects/one/performance');
  assert.equal(f.timers.size,0);assert.match(f.panel().innerHTML,/Сценарій.*RU/);assert.match(f.panel().innerHTML,/2 с/);
});
test('a delayed report cannot replace another project or modal',async()=>{
  const f=fixture();f.context.openPerformance();const old=f.panel();f.context.state.project={id:'two'};f.context.state.navigation++;
  f.waiting[0].resolve(report('running'));await settle();assert.equal(old.innerHTML,'loading');assert.equal(f.timers.size,0);
});
test('closing a live panel clears its next read and invalidates callbacks',async()=>{
  const f=fixture();f.context.openPerformance();f.waiting[0].resolve(report('running'));await settle();
  assert.equal(f.timers.size,1);const callback=[...f.timers][0];f.body.channelSettingsCleanup();
  assert.equal(f.timers.size,0);await callback();assert.equal(f.requests.length,1);
});
test('replacing the panel while a read is pending keeps the new result',async()=>{
  const f=fixture();f.context.openPerformance();const old=f.panel();f.context.openPerformance();
  f.waiting[1].resolve(report());await settle();const current=f.panel().innerHTML;
  f.waiting[0].resolve(report('running'));await settle();
  assert.equal(old.innerHTML,'loading');assert.equal(f.panel().innerHTML,current);assert.equal(f.timers.size,0);
});
test('connection failures retry only while the owning panel stays open',async()=>{
  const f=fixture();f.context.openPerformance();f.waiting[0].reject(new Error('offline'));await settle();
  assert.match(f.panel().innerHTML,/Повторюємо/);assert.equal(f.timers.size,1);
  const callback=[...f.timers][0];f.context.state.modalGeneration++;await callback();assert.equal(f.requests.length,1);
});
test('the time button follows project visibility',()=>{
  const f=fixture();assert.equal(f.button.hidden,false);f.context.state.project=null;f.context.updatePerformanceButton();assert.equal(f.button.hidden,true);
});
