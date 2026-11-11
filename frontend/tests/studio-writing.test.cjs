const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../studio-writing.js'),'utf8');
function fixture(api){
  const input={isConnected:true,disabled:true,value:'',dataset:{}},note={};
  const c=vm.createContext({api,$:id=>id==='studio-word-blacklist-input'?input:note});vm.runInContext(source,c);return {c,input,note};
}
test('global word list loads, keeps phrases, and saves only changed values',async()=>{
  const calls=[],h=fixture(async(url,method,body)=>{calls.push({url,method,body});return {settings:{word_blacklist:body?.settings.word_blacklist??['слово','Два слова']}};});
  await h.c.fillStudioWordBlacklist();assert.equal(h.input.disabled,false);assert.equal(h.input.value,'слово\nДва слова');
  await h.c.saveStudioWordBlacklist();assert.equal(calls.length,1);
  h.input.value='НОВЕ\nнове\nфраза з пробілами';await h.c.saveStudioWordBlacklist();
  assert.equal(calls.length,2);assert.equal(calls[1].method,'PATCH');assert.equal(JSON.stringify(calls[1].body.settings.word_blacklist),JSON.stringify(['НОВЕ','фраза з пробілами']));
});
test('unavailable old server does not silently lose typed edits or block unrelated settings',async()=>{
  const h=fixture(async()=>({settings:{youtube_root:'/tmp'}}));await h.c.fillStudioWordBlacklist();
  assert.equal(h.input.disabled,true);assert.match(h.note.textContent,/перезапуску/);await h.c.saveStudioWordBlacklist();
});
test('a failed save retains the editable blacklist for retry',async()=>{
  const h=fixture(async()=>{throw Error('Disk full')});h.input.disabled=false;h.input.value='Нове слово';
  await assert.rejects(h.c.saveStudioWordBlacklist(),/Disk full/);assert.equal(h.input.value,'Нове слово');
});
