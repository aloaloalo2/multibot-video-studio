const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../studio-folder.js'),'utf8');
function fixture(api){
  const input={value:'',dataset:{},disabled:true,isConnected:true},pick={disabled:true},feedback={textContent:'',classList:{add(){},remove(){}}};
  const nodes={'studio-folder-path':input,'studio-folder-pick':pick,'studio-folder-feedback':feedback};
  const section={isConnected:true,querySelector:selector=>nodes[selector.slice(1)]};
  const c=vm.createContext({$:id=>id==='studio-folder'?section:nodes[id],api});vm.runInContext(source,c);
  return {c,input,pick,feedback,section};
}
test('a chosen folder is staged and saved exactly once',async()=>{
  const calls=[];const f=fixture(async(url,method='GET',body)=>{calls.push({url,method,body});return url.endsWith('/pick')?{path:'/new'}:{settings:{youtube_root:method==='PATCH'?body.settings.youtube_root:'/old'}};});
  await f.c.fillStudioFolder();assert.equal(f.input.value,'/old');
  await f.pick.onclick();assert.equal(f.input.value,'/new');assert.equal(calls.filter(x=>x.method==='PATCH').length,0);
  assert.equal(await f.c.saveStudioFolder(),true);assert.equal(await f.c.saveStudioFolder(),false);
  assert.equal(calls.filter(x=>x.method==='PATCH').length,1);
});
test('late folder data cannot fill a replacement settings window',async()=>{
  let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));const pending=f.c.fillStudioFolder();
  f.section.isConnected=false;finish({settings:{youtube_root:'/late'}});await pending;
  assert.equal(f.input.value,'');assert.equal(f.input.disabled,true);
});
test('invalid folders stay visible for correction and never count as saved',async()=>{
  const f=fixture(async(_,method)=>{if(method==='PATCH')throw Error('Папка недоступна');return {settings:{youtube_root:'/old'}}});
  await f.c.fillStudioFolder();f.input.value='/missing';
  await assert.rejects(f.c.saveStudioFolder(),/недоступна/);assert.equal(f.input.dataset.saved,'/old');assert.equal(f.input.value,'/missing');assert.match(f.feedback.textContent,/недоступна/);
});
test('saving before the directory is loaded cannot erase its setting',async()=>{
  const f=fixture(()=>{throw Error('No request expected')});
  await assert.rejects(f.c.saveStudioFolder(),/папку YouTube/);
});
test('cancelling a native picker keeps the previous path',async()=>{
  const f=fixture(async(url)=>{if(url.endsWith('/pick'))throw Error('Папку не вибрано');return {settings:{youtube_root:'/old'}}});
  await f.c.fillStudioFolder();await f.pick.onclick();assert.equal(f.input.value,'/old');assert.equal(f.pick.disabled,false);assert.equal(await f.c.saveStudioFolder(),false);
});
