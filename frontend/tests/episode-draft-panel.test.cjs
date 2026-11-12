const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../episode-draft-panel.js'),'utf8');
function node(){
  let html='';return {isConnected:true,dataset:{},children:[],nodes:[],className:'',
    set innerHTML(value){html=value;this.children=[];this.nodes=[...value.matchAll(/<button\b([^>]*)>/g)].map(m=>({isConnected:true,disabled:m[1].includes('disabled'),dataset:{hook:/data-hook="(\d+)"/.exec(m[1])?.[1]},id:/id="([^"]+)"/.exec(m[1])?.[1]}));},
    get innerHTML(){return html},append(child){this.children.push(child)},prepend(child){this.children.unshift(child)},remove(){this.isConnected=false},
    querySelectorAll(){return [...this.nodes,...this.children.flatMap(child=>child.querySelectorAll?.('button')||[])]},
    querySelector(selector){if(selector==='button')return this.querySelectorAll()[0];if(selector==='.episode-draft-request-error')return this.children.find(child=>child.className==='episode-draft-request-error');return this.querySelectorAll().find(item=>'#'+item.id===selector);}
  };
}
const hooks={project_id:'p',stage:'openings',status:'done',target_words:2000,openings:[{text:'First hook'},{text:'Second hook'}]};
function fixture(api,initial=hooks){
  const root=node(),panel={dataset:{}},calls=[],timers=new Map(),state={project:{id:'p'},view:'editor',episodeDraft:initial};let seq=0,rendered=0;
  const c=vm.createContext({state,api:async(...args)=>{calls.push(args);return api(...args)},episodeDraftPending:d=>!!d?.project_id&&!d.completed&&!d.cancelled,
    createScriptEditingButton:()=>node(),episodeIcon:()=>'<svg></svg>',esc:s=>String(s),document:{createElement:node},voiceScriptDraft:{},crypto:{randomUUID:()=>`request-${++seq}`},
    renderProject(){rendered++},refreshProjects:async()=>{},setTimeout:fn=>{const id=++seq;timers.set(id,fn);return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,c);c.mountEpisodeDraftPanel(root,'p',initial,panel);
  return {c,root,panel,calls,state,timers,rendered:()=>rendered};
}
test('openings mount inside the script area and selecting one submits once, then updates to the saved script',async()=>{
  let release;
  const h=fixture(async(url,method)=>{
    if(method==='POST')return new Promise(done=>release=done);
    if(url.endsWith('/episode-draft'))return {...hooks,completed:true,script_saved:true};
    return {project:{id:'p',voice_script:{text:'Complete saved script'}}};
  });
  assert.equal(h.calls.length,0);assert.equal(h.root.children[0].nodes.length,2);
  assert.match(h.root.children[0].innerHTML,/Second hook/);
  const choose=h.root.children[0].nodes[1].onclick();
  await h.root.children[0].nodes[1].onclick();assert.equal(h.calls.length,1);
  assert.equal(h.calls[0][2].index,1);
  release({...hooks,stage:'script',status:'running'});await choose;
  assert.match(h.root.innerHTML,/Opus пише сценарій/);
  await [...h.timers.values()][0]();
  assert.equal(h.state.project.voice_script.text,'Complete saved script');assert.equal(h.rendered(),1);
});
test('late results cannot move a different project back to the old draft',async()=>{
  let release;
  const h=fixture(()=>new Promise(done=>release=done));
  const pending=h.root.children[0].nodes[0].onclick();h.state.project={id:'other'};
  release({...hooks,status:'running',stage:'script'});await pending;
  assert.equal(h.state.project.id,'other');assert.equal(h.rendered(),0);
});
test('a failed refresh keeps hooks and retries the same request receipt only after a click',async()=>{
  const h=fixture(async()=>{throw Error('Network failed')});
  await h.root.querySelector('#episode-draft-refresh').onclick();
  assert.equal(h.calls.length,1);assert.equal(h.timers.size,0);
  assert.match(h.root.children.find(child=>child.className==='episode-hook-options').innerHTML,/First hook/);
  await h.root.querySelector('#episode-draft-retry').onclick();
  assert.equal(h.calls.length,2);assert.equal(h.calls[0][2].request_id,h.calls[1][2].request_id);
});
test('disposing the script panel stops polling without cancelling the server job',()=>{
  const h=fixture(async()=>{}, {...hooks,status:'running'});
  assert.equal(h.timers.size,1);h.panel.episodeDraftDispose();assert.equal(h.timers.size,0);assert.equal(h.calls.length,0);
});

test('a temporary read failure keeps watching an active draft without repeating its paid action',async()=>{
  let attempts=0;
  const h=fixture(async()=>{if(!attempts++)throw Error('Temporary outage');return {...hooks,status:'running'}}, {...hooks,status:'running'});
  await [...h.timers.values()][0]();
  assert.equal(h.calls.length,1);assert.ok(h.root.querySelector('.episode-draft-request-error'));
  await [...h.timers.values()][0]();
  assert.equal(h.calls.length,2);assert.ok(h.calls.every(call=>call.length===1));
  assert.equal(h.root.querySelector('.episode-draft-request-error').isConnected,false);
});

test('an older poll cannot replace the script stage after a hook is selected',async()=>{
  let finish;
  const h=fixture(async(_,method)=>method==='POST'?{...hooks,stage:'script',status:'running'}:new Promise(resolve=>finish=resolve), {...hooks,status:'running'});
  const pending=[...h.timers.values()][0]();
  h.root.updateDraft(hooks);
  await h.root.children.find(child=>child.className==='episode-hook-options').nodes[0].onclick();
  finish(hooks);await pending;
  assert.equal(h.state.episodeDraft.stage,'script');assert.equal(h.state.episodeDraft.status,'running');
  assert.match(h.root.innerHTML,/Opus пише сценарій/);
});

test('failed self-review exposes a draft and resumes its author instead of metadata bypass',async()=>{
 const data={...hooks,stage:'script',status:'failed',script_saved:true,editing_status:'failed',author_session:{session_id:'same-author'}};
 const h=fixture(async()=>({...data,status:'running',stage:'editing'}),data);
 assert.match(h.root.innerHTML,/саморедактуру не завершено/);
 const retry=h.root.querySelector('#episode-draft-metadata');assert.equal(retry.textContent,'Продовжити саморедактуру · Opus');
 await retry.onclick();assert.equal(h.calls[0][2].action,'editing');assert.match(h.root.innerHTML,/Opus перевіряє й редагує свій сценарій/);
});
