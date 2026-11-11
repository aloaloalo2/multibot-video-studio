const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../services.js'),'utf8');
function fixture(api){
  const name={value:''},key={value:''},rows=[{value:'test-only-a',dataset:{provider:'first'}},{value:'test-only-b',dataset:{provider:'second'}}];
  const c=vm.createContext({$:id=>id==='service-key-name'?name:key,document:{querySelectorAll:()=>rows},api});
  vm.runInContext(source.slice(source.indexOf('async function saveTypedServiceKeys')),c);
  return {c,name,key,rows};
}
test('an incomplete custom service cannot silently close or partially save the form',async()=>{
  let calls=0;const {c,name}=fixture(async()=>calls++);name.value='Custom';
  await assert.rejects(c.saveTypedServiceKeys(),/Вставте ключ/);assert.equal(calls,0);
});
test('retry after a partial failure only sends unsaved service keys',async()=>{
  const calls=[];let failed=false;
  const {c,rows}=fixture(async(_,__,body)=>{calls.push(body.provider_id);if(body.provider_id==='second'&&!failed){failed=true;throw Error('offline')}});
  await assert.rejects(c.saveTypedServiceKeys(),/offline/);assert.equal(rows[0].value,'••••••••••••••••');
  await c.saveTypedServiceKeys();assert.deepEqual(calls,['first','second','second']);
});
