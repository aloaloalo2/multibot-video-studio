const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../episode-ideas.js'),'utf8');
const topics={status:'done',stage:'ideas',day:'today',target_words:1200,ideas:[{title:'A fresh title',uk:''},{title:'Another title',uk:''}],used_idea_indexes:[]};
const hooks={status:'done',stage:'openings',project_id:'project-a',target_words:1200,selected:{title:'A fresh title'},openings:[{text:'First hook',uk:''},{text:'Second hook',uk:''}]};
function element(){
  let html='';return {isConnected:true,hidden:false,value:'',readOnly:false,nodes:[],messages:[],classList:{add(){},remove(){}},focus(){},after(){},remove(){this.isConnected=false},setAttribute(key,value){this[key]=value},
    set innerHTML(value){html=value;this.nodes=[...value.matchAll(/<button\b([^>]*)>/g)].map(m=>({disabled:m[1].includes('disabled'),hidden:false,classList:{add(){},remove(){}},setAttribute(key,value){this[key]=value},dataset:{entry:/data-entry="([^"]+)"/.exec(m[1])?.[1],opening:/data-opening="(\d+)"/.exec(m[1])?.[1],idea:/data-idea="(\d+)"/.exec(m[1])?.[1]},id:/id="([^"]+)"/.exec(m[1])?.[1]}));if(value.includes('id="idea-words"'))this.words={value:'1200'};},
    get innerHTML(){return html},querySelector(s){return s==='#idea-words'?this.words:s==='button'?this.nodes[0]:this.nodes.find(b=>'#'+b.id===s)},
    querySelectorAll(s){return s==='button'?this.nodes:this.nodes.filter(b=>s==='[data-opening]'?b.dataset.opening!==undefined:b.dataset.idea!==undefined)},
    prepend(node){this.messages.unshift(node.innerHTML)}
  };
}
function harness(api){
  const root=element(),input=element(),actions=element(),backdrop=element(),calls=[],timers=[],selected=[];actions.innerHTML='<button>Create</button>';
  const modes=element(),referenceInput=element(),referenceBox=element(),note=element(),heading=element(),copy=element(),headerRefresh=element();
  modes.innerHTML='<button data-entry="title"></button><button data-entry="topics"></button><button data-entry="reference"></button>';
  let uuid=0;
  const context=vm.createContext({state:{channel:{id:'channel-a'}},$:id=>({'episode-ideas':root,'new-project-name':input,'modal-actions':actions,'modal-backdrop':backdrop,'modal-body':root,'modal-title':heading,'episode-entry-options':modes,'episode-reference-url':referenceInput,'episode-reference':referenceBox,'episode-reference-status':note,'episode-reference-copy':copy,'ideas-refresh':headerRefresh})[id],
    modal:(title)=>{context.title=title;backdrop.hidden=false},closeModal:()=>{backdrop.hidden=true;root.isConnected=false},
    api:async(...args)=>{calls.push(args);return api(...args)},esc:s=>s,projectCostIcons:{claude_code:'<svg></svg>'},status:()=>{},
    refreshProjects:async()=>{},showProjectList:()=>{},pollChannelActivity:()=>{},selectProject:async id=>selected.push(id),projectActivities:new Map(),
    crypto:{randomUUID:()=>`request-${++uuid}`},document:{createElement:element},setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout:()=>{}});
  vm.runInContext(source,context);return {context,root,input,actions,calls,timers,selected,modes,referenceInput,referenceBox,note,copy,headerRefresh};
}

test('New episode opens the empty own-title field without generating topics',async()=>{
  const h=harness(async()=>topics);await h.context.openNewEpisodeWizard();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/channels/channel-a/episode-ideas?view=topics');
  assert.equal(h.input.value,'');assert.equal(h.input.readOnly,false);assert.doesNotMatch(h.root.innerHTML,/Нові теми/);assert.doesNotMatch(h.root.innerHTML,/Ідеї DeepSeek/);
  assert.equal(h.actions.nodes[0].hidden,false);assert.equal(h.actions.nodes[0].disabled,true);assert.equal(h.input.hidden,false);
});
test('a project opens its saved hooks without any provider or catalog request',async()=>{
  const h=harness(()=>assert.fail('No network request for saved hooks'));
  await h.context.openNewEpisodeWizard({projectId:'project-a',draft:hooks});
  assert.equal(h.input.value,'A fresh title');assert.equal(h.input.readOnly,true);assert.equal(h.actions.nodes[0].hidden,true);
  assert.match(h.root.innerHTML,/First hook/);assert.match(h.root.innerHTML,/Нові зачини/);assert.match(h.root.innerHTML,/Скасувати/);
});
test('refreshing hooks sends one project-bound explicit request',async()=>{
  const h=harness(async()=>({...hooks,status:'running'}));await h.context.openNewEpisodeWizard({projectId:'project-a',draft:hooks});
  await h.root.querySelector('#openings-refresh').onclick();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/projects/project-a/episode-draft');
  assert.equal(h.calls[0][2].action,'openings');assert.equal(h.calls[0][2].refresh,true);assert.ok(h.calls[0][2].request_id);
  assert.match(h.root.innerHTML,/export-spinner/);assert.equal(h.timers.length,1);
});
test('selected topic creates a new episode only after pressing Create openings',async()=>{
  const h=harness(async(url,method)=>method==='POST'?({...hooks,status:'running'}):topics);
  await h.context.openNewEpisodeWizard();await h.modes.nodes[1].onclick();h.root.querySelectorAll('[data-idea]')[0].onclick();
  assert.equal(h.calls.length,2);assert.equal(h.input.value,'A fresh title');assert.equal(h.input.readOnly,false);
  h.input.value='A fresh title with my addition';
  await h.root.querySelector('#ideas-create-openings').onclick();
  assert.equal(h.calls.length,3);assert.equal(h.calls[2][2].new_episode,true);assert.equal(h.calls[2][2].index,0);assert.equal(h.calls[2][2].title,'A fresh title with my addition');
});
test('failed daily refresh shows an error without automatically repeating the paid request',async()=>{
  const h=harness(async(url,method)=>{if(method==='POST')throw new Error('Channel busy');return {...topics,stale:true};});
  await h.context.openNewEpisodeWizard();await h.modes.nodes[1].onclick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.calls.filter(c=>c[1]==='POST').length,1);assert.ok(h.root.messages.some(s=>s.includes('Channel busy')));
});
test('a failed attempt today never triggers an automatic repeat',async()=>{
  const h=harness(async()=>({...topics,stale:false,status:'failed',error:'Limit'}));await h.context.openNewEpisodeWizard();await h.modes.nodes[1].onclick();
  assert.equal(h.calls.length,2);assert.match(h.root.innerHTML,/Limit/);
});
test('yesterday failed ideas get one guarded attempt when the tab opens',async()=>{
  const h=harness(async(url,method)=>method==='POST'?{...topics,stale:false,status:'running'}:{...topics,stale:true,status:'failed',error:'Yesterday limit'});
  await h.context.openNewEpisodeWizard();await h.modes.nodes[1].onclick();await new Promise(resolve=>setImmediate(resolve));
  const posts=h.calls.filter(c=>c[1]==='POST');assert.equal(posts.length,1);assert.equal(posts[0][2].if_stale,true);assert.equal(posts[0][2].refresh,undefined);
  assert.match(h.root.innerHTML,/DeepSeek пропонує/);
});

test('closed project dialog ignores delayed polling',async()=>{
  const h=harness(()=>assert.fail('Closed draft must not poll'));await h.context.openNewEpisodeWizard({projectId:'project-a',draft:{...hooks,status:'running'}});
  h.context.closeModal();await h.timers[0]();assert.equal(h.calls.length,0);
});
test('cancelled and completed hooks do not reopen when selecting a project',()=>{
  const h=harness(()=>{});assert.equal(h.context.episodeDraftPending(hooks),true);
  assert.equal(h.context.episodeDraftPending({...hooks,cancelled:true}),false);
  assert.equal(h.context.episodeDraftPending({...hooks,completed:true}),false);
  assert.equal(h.context.episodeDraftPending({}),false);
});

test('source choice hides unrelated fields and selected topics remain editable',async()=>{
  const h=harness(async()=>topics);await h.context.openNewEpisodeWizard();
  h.modes.nodes[0].onclick();assert.equal(h.input.hidden,false);assert.equal(h.actions.hidden,true);assert.equal(h.actions.nodes[0].hidden,false);assert.equal(h.root.hidden,true);
  await h.modes.nodes[1].onclick();assert.equal(h.input.hidden,true);assert.equal(h.actions.hidden,true);
  h.root.querySelectorAll('[data-idea]')[0].onclick();h.input.value='Edited title';h.input.oninput();
  assert.equal(h.input.hidden,false);assert.equal(h.actions.hidden,true);assert.equal(h.root.hidden,false);
  assert.ok(h.root.querySelector('#ideas-create-openings'));
});

test('Copy imports title and reference without provider work, and openings submit edited title once',async()=>{
  const imported={id:'jNQXAC9IVRw',title:'Source title',author:'Source',thumbnail_url:'/local/reference.jpg'};
  const h=harness(async(url,method)=>url.endsWith('/idea-reference')?imported:method==='POST'?{...hooks,status:'running'}:topics);
  await h.context.openNewEpisodeWizard();h.modes.nodes[2].onclick();
  assert.equal(h.input.hidden,true);assert.equal(h.actions.hidden,true);assert.equal(h.root.hidden,true);
  h.referenceInput.value='https://youtu.be/jNQXAC9IVRw';h.referenceInput.oninput();
  assert.equal(h.calls.length,1); // pasting alone is free and starts nothing
  await h.copy.onclick();assert.equal(h.calls.length,2);assert.equal(h.input.value,'Source title');
  assert.equal(h.input.hidden,false);assert.match(h.root.innerHTML,/local\/reference.jpg/);
  h.input.value='My improved title';
  await h.root.querySelector('#reference-openings').onclick();
  assert.equal(h.calls[2][2].action,'clone_openings');assert.equal(h.calls[2][2].title,'My improved title');
  assert.equal(h.calls[2][2].reference_id,imported.id);
});

test('a stale reference response cannot replace another choice or title',async()=>{
  let resolve;
  const h=harness(async(url)=>url.endsWith('/idea-reference')?new Promise(done=>resolve=done):topics);
  await h.context.openNewEpisodeWizard();h.modes.nodes[2].onclick();
  h.referenceInput.value='https://youtu.be/jNQXAC9IVRw';h.referenceInput.oninput();
  const importing=h.copy.onclick();h.modes.nodes[0].onclick();h.input.value='My own draft';
  resolve({id:'jNQXAC9IVRw',title:'Late reply',thumbnail_url:'/ref.jpg'});await importing;
  assert.equal(h.input.value,'My own draft');assert.equal(h.input.hidden,false);assert.equal(h.root.hidden,true);
});

test('header refresh is scoped to ideas and duplicate clicks share the pending request',async()=>{
  let resolve;
  const h=harness(async(url,method)=>method==='POST'?new Promise(done=>resolve=done):topics);
  await h.context.openNewEpisodeWizard();assert.equal(h.headerRefresh.hidden,true);
  h.modes.nodes[2].onclick();assert.equal(h.headerRefresh.hidden,true);
  await h.modes.nodes[1].onclick();assert.equal(h.headerRefresh.hidden,false);
  const pending=h.headerRefresh.onclick();h.headerRefresh.onclick();
  assert.equal(h.calls.filter(call=>call[1]==='POST').length,1);
  resolve({...topics,status:'running',stage:'ideas'});await pending;
  assert.equal(h.headerRefresh.disabled,true);
});

test('own-title action enables only with text and preserves its draft between choices',async()=>{
  const h=harness(async()=>topics);await h.context.openNewEpisodeWizard();h.modes.nodes[0].onclick();
  assert.equal(h.actions.nodes[0].disabled,true);
  h.input.value='My saved title';h.input.oninput();assert.equal(h.actions.nodes[0].disabled,false);
  h.modes.nodes[1].onclick();h.modes.nodes[0].onclick();assert.equal(h.input.value,'My saved title');
});
