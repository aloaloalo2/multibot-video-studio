const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../space.js'),'utf8');

function fixture(api){
  const fields=Object.fromEntries(['total','open','review','free','cancel'].map(key=>[key,{textContent:'Звільнити місце',hidden:key==='review',disabled:false}]));
  const section={isConnected:true,querySelector:selector=>fields[selector.replace('#studio-space-','')],setAttribute(){},removeAttribute(){}};
  const messages=[];
  const context=vm.createContext({$:()=>section,api,status:message=>messages.push(message)});
  vm.runInContext(source,context);
  return {context,fields,section,messages};
}

test('global settings measures only on opening and reviews before deleting',async()=>{
  const calls=[];
  const {context,fields}=fixture(async(...args)=>{calls.push(args);return {total:2e9,busy:1};});
  await context.fillStudioSpace();
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/space');
  assert.match(fields.total.textContent,/2,0 ГБ/);assert.match(fields.total.textContent,/пропущено/);
  fields.open.onclick();assert.equal(fields.review.hidden,false);assert.equal(calls.length,1);
  fields.cancel.onclick();assert.equal(fields.review.hidden,true);assert.equal(calls.length,1);
});

test('empty caches disable cleanup and display zero',async()=>{
  const {context,fields}=fixture(async()=>({total:0}));
  await context.fillStudioSpace();assert.equal(fields.open.disabled,true);
  assert.match(fields.total.textContent,/0 МБ/);
});

test('successful cleanup refreshes size and reports partial skips',async()=>{
  let reads=0;
  const {context,fields,messages}=fixture(async(url,method)=>method==='POST'?{freed:1e9,busy:1,unavailable:1}:{total:reads++?0:1e9});
  await context.fillStudioSpace();fields.open.onclick();await fields.free.onclick();
  assert.equal(reads,2);assert.equal(fields.review.hidden,true);assert.equal(fields.open.disabled,true);
  assert.match(messages[0],/1,0 ГБ/);assert.match(messages[0],/не вдалося очистити/);
});

test('late replies never reopen closed settings',async()=>{
  let resolve;
  const {context,fields,section}=fixture(()=>new Promise(done=>{resolve=done;}));
  const pending=context.fillStudioSpace();section.isConnected=false;resolve({total:1e9});await pending;
  assert.equal(fields.total.textContent,'Звільнити місце');
});

test('a failed scan can be retried without deletion',async()=>{
  let reads=0;
  const {context,fields}=fixture(async()=>{if(!reads++)throw Error('Недоступно');return {total:1e9};});
  await context.fillStudioSpace();assert.equal(fields.open.textContent,'Перевірити ще раз');
  await fields.open.onclick();assert.equal(fields.open.textContent,'Звільнити місце');
  assert.equal(fields.open.disabled,false);assert.equal(reads,2);
});
