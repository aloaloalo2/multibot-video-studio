const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../director.js'),'utf8');

function setup(){
  let reply;
  const request={status:'in_progress',started_at:100};
  const state={project:{id:'p',production_request:request}};
  const c=vm.createContext({state,Date:{now:()=>400000},esc:text=>text,exportSpinner:'<i></i>',
    api:()=>new Promise(resolve=>reply=resolve)});
  vm.runInContext(source.slice(source.indexOf('const teamRoles='),source.indexOf('async function pollProduction(')),c);
  const button={isConnected:true,setAttribute(){}};
  return {c,state,request,button,reply:value=>reply(value)};
}

test('stale production activity clearly shows inactivity beside the actor and ready frame count',async()=>{
  const {c,request,button,reply}=setup();
  c.renderMakeStatus(button,'p',request,45,45);
  reply({activity:[{t:101,who:'opus',text:'Готує допоміжні файли'}]});
  await Promise.resolve();await Promise.resolve();
  assert.match(button.innerHTML,/Режисер · готує матеріали/);
  assert.match(button.innerHTML,/Без нових дій 4 хв/);
  assert.match(button.innerHTML,/45 з 45/);
  assert.match(button.title,/Час завершення ще невідомий/);
});

test('a late activity reply cannot turn a completed run back into live work',async()=>{
  const {c,state,request,button,reply}=setup();
  c.renderMakeStatus(button,'p',request,45,45);
  const before=button.innerHTML;
  state.project.production_request={...request,status:'done'};
  reply({activity:[{t:399,who:'opus',text:'Пише сцени'}]});
  await Promise.resolve();await Promise.resolve();
  assert.equal(button.innerHTML,before);
});
