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
  assert.equal(f.timers.size,0);assert.match(f.panel().innerHTML,/Сценарій/);
  // minutes and hours only since ac50581: two seconds of work read as «<1 хв»
  assert.match(f.panel().innerHTML,/performance-duration" role="cell">&lt;1 хв</);
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
  // no per-run status or stage breakdown; the only fold is «Інше» for processes under a minute (ac50581, aad9026)
  assert(!html.includes('Перервано'));assert(!html.includes('Підготовка'));assert(!html.includes('performance-stage'));
  assert.deepEqual(html.match(/<details[^>]*>/g),['<details class="performance-small">']);assert.match(html,/<summary><span>Інше<\/span>/);
});
test('new reports are sorted defensively and keep tiny tasks and previews out of the list',()=>{
  const f=fixture();
  // the backend sends its runs beside the processes (job_timing.overview); since ac50581 the time comes from the runs
  // and a process lends its row only the cost, or a row of its own when it has a cost and no time (kit, 07e6c14)
  const cost={recorded:true,providers:{claude_code:{requests:1,usd:35}}};
  const rows=f.context.performanceRows({
    runs:[{workflow:'script',elapsed_ms:5000},{workflow:'production',elapsed_ms:9000},{workflow:'thumbnail',elapsed_ms:20000},{workflow:'metadata',elapsed_ms:1000}],
    processes:[{id:'script',workflow:'script',label:'Сценарій',active_ms:5000},{id:'production',workflow:'production',label:'Кадри',active_ms:9000,cost},{id:'thumbnail',workflow:'thumbnail',active_ms:20000},{id:'metadata',workflow:'metadata',active_ms:1000}]});
  assert.deepEqual(JSON.parse(JSON.stringify(rows.map(row=>row.id))),['production','script']);
  assert.equal(rows[0].cost,cost);
  const kit=f.context.performanceRows({runs:[],processes:[{workflow:'kit',active_ms:0,cost},{workflow:'thumbnail',active_ms:0,cost}]});
  assert.deepEqual(JSON.parse(JSON.stringify(kit.map(row=>[row.id,row.cost_only]))),[['kit',true]]);
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
test('a failed frame run keeps its time as work and the longest process leads',()=>{
  // «Галактики», 15 November 2026: 17.8 min of drawn frames read as a failed attempt
  const f=fixture(),rows=f.context.performanceRows({runs:[
    {workflow:'script',elapsed_ms:120000,status:'complete'},
    {workflow:'production',elapsed_ms:1068000,status:'failed'},
    {workflow:'translation',elapsed_ms:60000,status:'failed'},
  ]});
  assert.deepEqual(JSON.parse(JSON.stringify(rows.map(row=>[row.workflow,row.active_ms,row.lost_ms]))),
    // every spinner minute counts, a failed attempt too; the row still says how much failed (19 November 2026)
    [['production',1068000,0],['script',120000,0],['translation',60000,60000]]);
});
test('languages voiced side by side count their clock time once',()=>{
  // CORBIN, 15 November 2026: pl and ru from 20:10 to 20:28 and uk and es from 07:46 to 07:49 read as 42 min
  const f=fixture(),min=60000,at=s=>s;
  const rows=f.context.performanceRows({runs:[
    {workflow:'language_voice',language:'pl',status:'complete',started_at:at(1000),elapsed_ms:18*min},
    {workflow:'language_voice',language:'ru',status:'complete',started_at:at(1008),elapsed_ms:18*min},
    {workflow:'language_voice',language:'uk',status:'complete',started_at:at(50000),elapsed_ms:3*min},
    {workflow:'language_voice',language:'es',status:'complete',started_at:at(50002),elapsed_ms:3*min,stages:{queue:{ms:2000}}},
  ]});
  assert.equal(Math.round(rows[0].active_ms/1000),18*60+8+3*60+2);
});
test('translations run beside the pipeline and stay out of the total time',()=>{
  const f=fixture(),min=60000;
  const html=f.context.performanceMarkup({runs:[
    {workflow:'narration',status:'complete',started_at:1000,elapsed_ms:10*min},
    {workflow:'translation',status:'complete',started_at:2000,elapsed_ms:4*min},
    {workflow:'language_voice',status:'complete',started_at:3000,elapsed_ms:20*min},
  ]});
  assert.match(html,/performance-total"><strong>Разом<\/strong><span class="performance-duration">10 хв</);
  assert.equal((html.match(/паралельно, не входить у «Разом»/g)||[]).length,2);
});
test('the openings count with the script and a process under two minutes goes to «Інше»',()=>{
  const {context}=fixture();
  const data={runs:[
    {workflow:'openings',status:'complete',elapsed_ms:240000,started_at:1000},
    {workflow:'script',status:'complete',elapsed_ms:600000,started_at:2000},
    {workflow:'metadata',status:'complete',elapsed_ms:90000,started_at:3000}],
    processes:[{workflow:'openings',cost:{recorded:true,providers:{openrouter:{requests:1,usd:0.5}}}},
               {workflow:'script',cost:{recorded:true,providers:{openrouter:{requests:2,usd:1}}}}]};
  const rows=context.performanceRows(data);
  assert.equal(rows.map(row=>row.workflow).join(),'script,metadata');
  assert.equal(rows[0].active_ms,840000);
  assert.equal(rows[0].cost.providers.openrouter.usd,1.5);
  const markup=context.performanceMarkup(data);
  assert.ok(markup.indexOf('Метадані')>markup.indexOf('Інше'));   // 1.5 minutes sits under «Інше»
});
