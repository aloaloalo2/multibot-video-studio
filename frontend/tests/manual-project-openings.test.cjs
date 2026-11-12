const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../episode-draft-panel.js'),'utf8');
function fixture({supported=true}={}){
 let dialog,rendered=0,closed=0;
 const calls=[],project={id:'manual',name:'What If Humans Could Live Forever?'},state={project,navigation:1,modalGeneration:1};
 const c=vm.createContext({state,crypto:{randomUUID:()=> 'receipt'},esc:s=>s,flushScriptDraft:async()=>({text:''}),episodeDraftPending:()=>false,
  api:async(...args)=>{calls.push(args);return args[0]==='/api/health'?{manual_project_openings:supported}:{project_id:'manual',stage:'openings',status:'running'};},
  modal:(title,body,actions)=>{state.modalGeneration++;dialog={title,body,action:actions[0]};},
  $:()=>({value:'3200'}),closeModal:()=>closed++,renderProject:()=>rendered++});
 vm.runInContext(source,c);
 return {c,state,project,calls,dialog:()=>dialog,rendered:()=>rendered,closed:()=>closed};
}
test('manual project button opens a word target then submits openings to that same project',async()=>{
 const h=fixture();await h.c.openManualProjectOpenings(h.project);
 assert.match(h.dialog().body,/What If Humans Could Live Forever/);
 assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/health');
 await h.dialog().action.run();
 assert.equal(h.calls[1][0],'/api/projects/manual/episode-draft');
 assert.equal(h.calls[1][2].action,'openings');assert.equal(h.calls[1][2].target_words,3200);
 assert.equal(h.state.episodeDraft.project_id,'manual');assert.equal(h.rendered(),1);assert.equal(h.closed(),1);
});
test('a busy older server disables generation until its safe update is active',async()=>{
 const h=fixture({supported:false});await h.c.openManualProjectOpenings(h.project);
 assert.equal(h.dialog().action.enabled(),false);assert.match(h.dialog().body,/після завершення/);assert.equal(h.calls.length,1);
});
test('a different modal or project cannot receive a stale openings response',async()=>{
 const h=fixture();await h.c.openManualProjectOpenings(h.project);
 let release;h.c.api=()=>new Promise(resolve=>release=resolve);
 const pending=h.dialog().action.run();await new Promise(resolve=>setImmediate(resolve));
 h.state.modalGeneration++;release({project_id:'manual',stage:'openings',status:'running'});await pending;
 assert.equal(h.closed(),0);assert.equal(h.rendered(),0);assert.equal(h.state.episodeDraft,undefined);
});
