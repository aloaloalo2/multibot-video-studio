const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../episode-ideas.js'),'utf8');
const topics={status:'done',stage:'ideas',day:'today',target_words:1200,ideas:[{title:'A fresh title',uk:''},{title:'Another title',uk:''}],used_idea_indexes:[]};
const hooks={status:'done',stage:'openings',project_id:'project-a',target_words:1200,selected:{title:'A fresh title'},openings:[{text:'First hook',uk:''},{text:'Second hook',uk:''}]};
function element(){
  let html='';return {isConnected:true,hidden:false,value:'',readOnly:false,nodes:[],messages:[],classList:{add(){},remove(){}},
    set innerHTML(value){html=value;this.nodes=[...value.matchAll(/<button\b([^>]*)>/g)].map(m=>({disabled:m[1].includes('disabled'),hidden:false,dataset:{opening:/data-opening="(\d+)"/.exec(m[1])?.[1],idea:/data-idea="(\d+)"/.exec(m[1])?.[1]},id:/id="([^"]+)"/.exec(m[1])?.[1]}));if(value.includes('id="idea-words"'))this.words={value:'1200'};},
    get innerHTML(){return html},querySelector(s){return s==='#idea-words'?this.words:s==='button'?this.nodes[0]:this.nodes.find(b=>'#'+b.id===s)},
    querySelectorAll(s){return s==='button'?this.nodes:this.nodes.filter(b=>s==='[data-opening]'?b.dataset.opening!==undefined:b.dataset.idea!==undefined)},
    prepend(node){this.messages.unshift(node.innerHTML)}
  };
}
function harness(api){
  const root=element(),input=element(),actions=element(),backdrop=element(),calls=[],timers=[],selected=[];actions.innerHTML='<button>Create</button>';
  let uuid=0;
  const context=vm.createContext({state:{channel:{id:'channel-a'}},$:id=>({'episode-ideas':root,'new-project-name':input,'modal-actions':actions,'modal-backdrop':backdrop})[id],
    modal:(title)=>{context.title=title;backdrop.hidden=false},closeModal:()=>{backdrop.hidden=true;root.isConnected=false},
    api:async(...args)=>{calls.push(args);return api(...args)},esc:s=>s,projectCostIcons:{claude_code:'<svg></svg>'},status:()=>{},
    refreshProjects:async()=>{},showProjectList:()=>{},pollChannelActivity:()=>{},selectProject:async id=>selected.push(id),projectActivities:new Map(),
    crypto:{randomUUID:()=>`request-${++uuid}`},document:{createElement:element},setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout:()=>{}});
  vm.runInContext(source,context);return {context,root,input,actions,calls,timers,selected};
}

test('New episode loads topics only, leaving title empty',async()=>{
  const h=harness(async()=>topics);await h.context.openNewEpisodeWizard();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/channels/channel-a/episode-ideas?view=topics');
  assert.equal(h.input.value,'');assert.equal(h.input.readOnly,false);assert.match(h.root.innerHTML,/Нові теми/);
  assert.equal(h.actions.nodes[0].hidden,false);
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
  await h.context.openNewEpisodeWizard();h.root.querySelectorAll('[data-idea]')[0].onclick();
  assert.equal(h.calls.length,1);assert.equal(h.input.value,'A fresh title');assert.equal(h.input.readOnly,false);
  h.input.value='A fresh title with my addition';
  await h.root.querySelector('#ideas-create-openings').onclick();
  assert.equal(h.calls.length,2);assert.equal(h.calls[1][2].new_episode,true);assert.equal(h.calls[1][2].index,0);assert.equal(h.calls[1][2].title,'A fresh title with my addition');
});
test('failed daily refresh shows an error without automatically repeating the paid request',async()=>{
  const h=harness(async(url,method)=>{if(method==='POST')throw new Error('Channel busy');return {...topics,stale:true};});
  await h.context.openNewEpisodeWizard();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.calls.filter(c=>c[1]==='POST').length,1);assert.ok(h.root.messages.some(s=>s.includes('Channel busy')));
});
test('a saved failed refresh with stale topics never triggers an automatic repeat',async()=>{
  const h=harness(async()=>({...topics,stale:true,status:'failed',error:'Limit'}));await h.context.openNewEpisodeWizard();
  assert.equal(h.calls.length,1);assert.match(h.root.innerHTML,/Limit/);
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
