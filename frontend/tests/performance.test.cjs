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
  assert.equal(f.timers.size,0);assert.match(f.panel().innerHTML,/Сценарій/);assert.match(f.panel().innerHTML,/2 с/);
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

test('main processes merge resumed attempts, subtract idle spans and sort by active duration',()=>{
  const f=fixture(),rows=f.context.performanceRows({runs:[
    {workflow:'script',elapsed_ms:10000,stages:{queue:{ms:4000}}},
    {workflow:'script',elapsed_ms:9000,started_at:100000,stages:{pause:{ms:5000}},status:'stopped'},
    {workflow:'production',elapsed_ms:30000},
    {workflow:'thumbnail',elapsed_ms:900000},
    {workflow:'language_thumbnail',elapsed_ms:800000},
    {workflow:'metadata',elapsed_ms:1000},
    {workflow:'language_voice',elapsed_ms:3000},
    {workflow:'language_save',elapsed_ms:2000},
  ]});
  assert.deepEqual(JSON.parse(JSON.stringify(rows.map(row=>[row.workflow,row.active_ms]))),[['production',30000],['script',10000],['language_voice',5000]]);
  const html=f.context.performanceMarkup({runs:[{workflow:'script',elapsed_ms:2000,status:'interrupted',stages:{preparation:{ms:1000}}}]});
  assert(!html.includes('Перервано'));assert(!html.includes('Підготовка'));assert(!html.includes('<details'));
});
test('new reports are sorted defensively and keep tiny tasks and previews out of the list',()=>{
  const f=fixture();
  const rows=f.context.performanceRows({processes:[{id:'s',workflow:'script',label:'Сценарій',active_ms:5000},{id:'p',workflow:'production',label:'Кадри',active_ms:9000},{id:'t',workflow:'thumbnail',active_ms:20000},{id:'m',workflow:'metadata',active_ms:1000}]});
  assert.deepEqual(JSON.parse(JSON.stringify(rows.map(row=>row.id))),['p','s']);
});
test('costs use the saved subscription convention and explain tokens without adding another row',()=>{
  const f=fixture(),cost=f.context.performanceCost({recorded:true,providers:{claude_code:{requests:1,usd:35},openrouter:{requests:1,usd:.02}},tokens:{input:100,output:200,cache_read:300}});
  assert.equal(cost.label,'≈ $1.02');assert.match(cost.title,/API-еквівалент \$35.00 ÷ 35/);assert.match(cost.title,/вхід 100, вихід 200, читання кешу 300/);
  assert.equal(f.context.performanceCost({recorded:true,providers:{heygen:{requests:139,usd:0,estimated:true}}}).label,'$0.00');
  assert.equal(f.context.performanceCost({recorded:false}).label,'Немає даних');
  assert.equal(f.context.performanceCost({recorded:true,providers:{openrouter:{requests:1,usd:0,unknown:1}}}).label,'Немає даних');
  assert.equal(f.context.performanceCost({recorded:true,providers:{openrouter:{requests:2,usd:1,unknown:1}}}).label,'≈ $1.00+');
});
test('only ongoing preview work never keeps the work-time window polling',async()=>{
  const f=fixture();f.context.openPerformance();f.waiting[0].resolve({runs:[{workflow:'thumbnail',status:'running',elapsed_ms:10000}]});await settle();
  assert.equal(f.timers.size,0);assert(!f.panel().innerHTML.includes('performance-row'));
});
test('an unchanged live report preserves the displayed rows',async()=>{
  const f=fixture();f.context.openPerformance();const data=report('running');f.waiting[0].resolve(data);await settle();
  const panel=f.panel();let writes=0,markup=panel.innerHTML;
  Object.defineProperty(panel,'innerHTML',{get:()=>markup,set:value=>{writes++;markup=value;}});
  const pending=[...f.timers][0]();f.waiting[1].resolve(data);await pending;assert.equal(writes,0);
});
