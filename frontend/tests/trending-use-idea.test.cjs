const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../trending-videos.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;return {promise:new Promise((r,j)=>{resolve=r;reject=j;}),resolve:value=>resolve(value),reject:error=>reject(error)};};
function harness({submitReply,recommendation}={}){
  const fields={channel:{value:'own',disabled:false},title:{value:'Exact competitor title',disabled:false},words:{value:'2000',disabled:false},use_thumbnail:{checked:true,disabled:false},use_hero:{checked:true,disabled:false,closest:()=>({title:''})}};
  const note={hidden:true,textContent:''},button={disabled:false},calls=[],navigations=[];
  const root={isConnected:true,querySelector:selector=>selector==='.trend-idea-feedback'?note:fields[selector.match(/name="([^"]+)"/)[1]],querySelectorAll:()=>Object.values(fields)};
  const state={channels:[{id:'own',name:'Our channel',hero_reference:{url:'/host.png'}},{id:'other',name:'Other'}],navigation:3,modalGeneration:0};
  const elements={'modal-backdrop':{hidden:false},'modal-body':{querySelector:()=>root},'modal-actions':{querySelector:()=>button}};
  const h={fields,note,button,calls,navigations,root,state,action:null,html:'',used:[]};
  const context=vm.createContext({state,bindTitleTranslation:(input,options)=>{h.translation=options;return {refresh(){},dispose(){}};},crypto:{randomUUID:()=> 'stable-request-id'},esc:String,$:id=>elements[id],modal:(title,html,actions)=>{state.modalGeneration++;h.html=html;h.action=actions[0];},closeModal:()=>{state.modalGeneration++;root.isConnected=false;},api:async(path,method='GET',body)=>{
    calls.push({path,method,body});
    if(path==='/api/health')return {trending_use_idea:true};
    if(method==='POST')return submitReply?submitReply.promise:{project_id:'project'};
    return recommendation?recommendation.promise:{target_words:1350};
  },selectChannel:async id=>{navigations.push(['channel',id]);return true;},selectProject:async id=>navigations.push(['project',id])});
  vm.runInContext(source.slice(source.indexOf('function openTrendingIdea')),context);
  h.open=()=>context.openTrendingIdea({id:'abcdefghijk',title:'Exact competitor title',title_uk:'Український заголовок',for_channels:[{id:'own'}]},'own',()=>h.used.push('abcdefghijk'));
  return h;
}
test('opening the idea dialog reads settings without creating a project or starting an author',async()=>{
  const h=harness();h.open();await tick();
  assert.ok(h.calls.every(c=>c.method==='GET'));
  assert.ok(h.html.includes('name="use_thumbnail" type="checkbox" checked'));
  assert.ok(h.html.includes('value="Exact competitor title"'));
  assert.equal(h.fields.words.value,1350);
  assert.equal(h.button.disabled,false);
  assert.deepEqual(h.used,[]);
});
test('unchecked source sends title-only choice and duplicate clicks share one request',async()=>{
  const reply=deferred(),h=harness({submitReply:reply});h.open();await tick();h.fields.use_thumbnail.checked=false;
  const first=h.action.run();await h.action.run();
  const posts=h.calls.filter(c=>c.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].body.use_thumbnail,false);assert.equal(posts[0].body.title,'Exact competitor title');
  assert.equal(posts[0].body.channel_id,'own');assert.equal(posts[0].body.request_id,'stable-request-id');
  reply.resolve({project_id:'created'});await first;
  assert.deepEqual(h.navigations,[['channel','own'],['project','created']]);
  assert.deepEqual(h.used,['abcdefghijk']);
});
test('a late creation response does not navigate after the author leaves the dialog',async()=>{
  const reply=deferred(),h=harness({submitReply:reply});h.open();await tick();
  const first=h.action.run();h.state.modalGeneration++;
  reply.resolve({project_id:'created'});await first;assert.deepEqual(h.navigations,[]);
  assert.deepEqual(h.used,['abcdefghijk']);
});
test('a failed creation keeps the source available',async()=>{
  const reply=deferred(),h=harness({submitReply:reply});h.open();await tick();
  const pending=h.action.run();reply.reject(new Error('Creation unavailable'));await pending;
  assert.deepEqual(h.used,[]);assert.equal(h.note.textContent,'Creation unavailable');assert.equal(h.button.disabled,false);
});
test('a late length recommendation keeps the author’s own word target',async()=>{
  const recommendation=deferred(),h=harness({recommendation});h.open();
  h.fields.words.value='4200';h.fields.words.oninput();recommendation.resolve({target_words:1300});await tick();
  assert.equal(h.fields.words.value,'4200');
});
test('creating openings waits for the chosen title translation',async()=>{
  const h=harness();h.open();await tick();h.translation.onBusy(true);
  assert.equal(h.button.disabled,true);await h.action.run();assert.ok(h.calls.every(c=>c.method==='GET'));
  h.translation.onBusy(false);assert.equal(h.button.disabled,false);
});

test('host choice reaches the idea request and resets when the selected channel has no host',async()=>{
  const h=harness();h.open();await tick();
  h.fields.use_hero.checked=false;await h.action.run();
  assert.equal(h.calls.find(c=>c.method==='POST').body.use_hero,false);
  const other=harness();other.open();await tick();other.fields.channel.value='other';other.fields.channel.onchange();
  assert.equal(other.fields.use_hero.checked,false);assert.equal(other.fields.use_hero.disabled,true);
});
