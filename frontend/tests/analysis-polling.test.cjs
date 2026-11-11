const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../analysis.js'),'utf8');
function fixture(api){
  const node=()=>({isConnected:true,hidden:false,disabled:false,events:{},children:[],files:[],value:'',append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(k,fn){this.events[k]=fn},querySelector(){return null}});
  const nodes=Object.fromEntries(['speech-analysis-state','plan-import-feedback','plan-import-file','modal-actions','modal-backdrop','modal-body'].map(id=>[id,node()]));
  const button=node(),calls=[],timers=new Map(),selected=[];let next=0;
  nodes['modal-actions'].querySelector=()=>button;
  const state={project:{id:'p'},plan:{script:'Saved script.',frames:[]},assets:[],navigation:1,modalGeneration:1};
  const c=vm.createContext({state,$:id=>nodes[id],api:async(...args)=>{calls.push(args);return api(...args)},modal:(title,body,actions)=>{c.actions=actions},closeModal:()=>{nodes['modal-backdrop'].hidden=true;state.modalGeneration++},selectProject:async id=>selected.push(id),status(){},esc:x=>x,
    document:{createElement:node},appendSpeechReport(){},speechStageNames:{recognizing:'Recognizing'},setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,delay});return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source.slice(source.indexOf('async function openMediaTimingImport(')),c);
  return {c,state,nodes,button,calls,timers,selected};
}
test('late initial recognition read cannot attach an old report to another project',async()=>{
  let finish;const h=fixture(()=>new Promise(resolve=>finish=resolve));
  const opening=h.c.openMediaTimingImport();h.state.project={id:'other'};h.state.navigation++;
  finish({job:{status:'running'},report:{old:true}});await opening;
  assert.equal(h.state.analysis,undefined);assert.equal(h.timers.size,0);
});
test('temporary GET failure keeps active analysis locked and polling recovers without another start',async()=>{
  let count=0;const h=fixture(async()=>{count++;if(count===2)throw Error('Connection lost');return {job:{status:count===3?'complete':'running',stage:'recognizing',progress:30}}});
  await h.c.openMediaTimingImport();assert.equal(h.button.disabled,true);assert.equal(h.nodes['plan-import-file'].disabled,true);
  let timer=[...h.timers.values()].at(-1);await timer.fn();
  assert.equal(h.button.disabled,true);assert.equal(h.nodes['plan-import-file'].disabled,true);
  timer=[...h.timers.values()].at(-1);await timer.fn();
  assert.equal(h.nodes['plan-import-file'].disabled,false);assert.ok(h.calls.every(c=>c.length===1));
});
test('finishing a timing import cannot close a new dialog or navigate back to the previous project',async()=>{
  let finish;const h=fixture(async(url,method)=>method==='POST'?new Promise(resolve=>finish=resolve):{job:null});
  await h.c.openMediaTimingImport();
  h.nodes['plan-import-file'].files=[{name:'timings.json',text:async()=>JSON.stringify({duration:2,sentences:[]})}];
  await h.nodes['plan-import-file'].events.change();const saving=h.c.actions[0].run();
  h.state.modalGeneration++;h.state.navigation++;h.state.project={id:'other'};
  finish({project:{id:'p'}});await saving;
  assert.equal(h.nodes['modal-backdrop'].hidden,false);assert.deepEqual(h.selected,[]);
});
test('opening the import dialog for an already finished analysis does not close it automatically',async()=>{
  const h=fixture(async()=>({job:{status:'complete'},report:{applied:true}}));
  await h.c.openMediaTimingImport();assert.equal(h.nodes['modal-backdrop'].hidden,false);assert.deepEqual(h.selected,[]);
});

test('verified generated assembly explains sentence order without an ASR order alarm',()=>{
  function node(){return {children:[],append(...items){this.children.push(...items)}};}
  const c=vm.createContext({document:{createElement:node},esc:x=>x,speechIssueNames:{}});
  vm.runInContext(source.slice(source.indexOf('function appendSpeechReport('),source.indexOf('async function openMediaTimingImport(')),c);
  const report={applied:true,timing_source:'generated_takes',sequence_verification:{version:2},word_match_percent:80,matched_phrases:2,phrase_count:2,phrases:[],source:{name:'voice.flac'},differences:[{kind:'moved',note:'ASR uncertain order'}]};
  const generated=node();c.appendSpeechReport(generated,report,{transcript:false});
  assert.equal(generated.children[0].children[0].textContent,'Порядок речень підтверджено');
  assert.equal(generated.children[0].children.some(n=>n.className==='speech-order'),false);
  const uploaded=node();c.appendSpeechReport(uploaded,{...report,applied:false,timing_source:null},{transcript:false});
  assert.equal(uploaded.children[0].children.some(n=>n.className==='speech-order'),true);
});
