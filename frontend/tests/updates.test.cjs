const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../updates.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(initial,handler=async()=>({status:'restarting'})){
  let current=initial,click;const calls=[],modals=[],elements=new Map(),timers=new Map();let nextTimer=0;
  const classes=()=>({add(){},remove(){},toggle(){}});
  const button={classList:classes(),addEventListener(name,run){click=run},getBoundingClientRect:()=>({bottom:20,right:100})};elements.set('studio-update',button);
  const c=vm.createContext({document:{getElementById:id=>elements.get(id),createElement:()=>({style:{},classList:classes(),setAttribute(){}}),body:{append(el){elements.set(el.id,el)}}},window:{innerWidth:1000},
    fetch:async()=>({ok:true,json:async()=>current}),api:async(...args)=>{calls.push(args);return handler(...args)},
    esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
    modal:(...args)=>modals.push(args),location:{reload(){}},setTimeout:run=>{const id=++nextTimer;timers.set(id,run);return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,c);return {c,button,calls,modals,elements,click:()=>click(),set:value=>current=value};
}
test('local code states and failed builds offer one Update action without a blocking dialog',async()=>{
  for(const status of ['available','local_changes','diverged','other_branch','update_failed']){
    const h=fixture({status,boot:'one',error:status==='update_failed'?'Missing package':undefined});await settle();
    assert.equal(h.button.hidden,false);assert.match(h.button.innerHTML,/Оновити студію/);assert.doesNotMatch(h.button.innerHTML,/зупинен/);
    h.click();await settle();assert.equal(h.modals.length,0);assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/update/apply');assert.equal(h.calls[0][1],'POST');
  }
});
test('protected personal files still remain untouched and the reason is escaped',async()=>{
  const h=fixture({status:'unsafe_update',files:['<b>.key'],boot:'one'});await settle();h.click();
  assert.equal(h.calls.length,0);assert.equal(h.modals.length,1);assert.match(h.modals[0][1],/&lt;b&gt;.key/);
});
test('a busy update stays queued without another apply request',async()=>{
  const h=fixture({status:'available',boot:'one'},async()=>({status:'queued',reason:'Зараз іде експорт'}));await settle();h.click();await settle();
  assert.match(h.button.innerHTML,/Оновлю після роботи/);h.click();await settle();assert.equal(h.calls.length,1);
});
test('a genuine apply error leaves an enabled retry and a readable note',async()=>{
  const h=fixture({status:'available',boot:'one'},async()=>{throw Error('Previous files restored')});await settle();h.click();await settle();
  assert.equal(h.button.disabled,false);assert.match(h.elements.get('studio-update-note').textContent,/Previous files restored/);assert.equal(h.modals.length,0);
});
