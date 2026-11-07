const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('selecting a frame preserves the current playhead instead of seeking to its start',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../groups.js'),'utf8');
  const state={playhead:140,selected:'old',multiSelection:['old']};
  const c=vm.createContext({state,clearTransitionSelection(){},renderGroupingControls(){},renderInspector(){},renderPreview(){},
    document:{querySelectorAll:()=>[]},groupBounds:()=>assert.fail('Selection must not seek')});
  vm.runInContext(source.slice(source.indexOf('function selectFrameGroup('),source.indexOf('function expandFrameGroup(')),c);
  c.selectFrameGroup({id:'frame-three'});
  assert.equal(state.playhead,140);
  assert.equal(state.selectedGroup,'frame-three');
});

test('selecting an individual timeline clip also preserves the playhead',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../universal.js'),'utf8');
  const state={playhead:140};const clip={id:'clip',start:22};
  const c=vm.createContext({state,universalClips:()=>[clip],layers:()=>[{id:'layer',clips:[clip]}],seconds:Number,
    renderTimeline(){},renderInspector(){},renderPreview(){},status(){},clipLabel:()=>''});
  vm.runInContext(source.slice(source.indexOf('function selectUniversalClip('),source.indexOf('function renderUniversalTimeline(')),c);
  c.selectUniversalClip('clip');
  assert.equal(state.playhead,140);assert.equal(state.selected,'clip');assert.equal(state.activeLayer,'layer');
  c.selectUniversalClip('clip',true);
  assert.equal(state.playhead,22);
});

test('Command-click includes the previously selected frame in the repair selection',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../groups.js'),'utf8');
  const groups=[{id:'g3',title:'Кадр 3',clip_ids:['c3']},{id:'g5',title:'Кадр 5',clip_ids:['c5']}];
  const state={selectedGroup:'g3',multiSelection:[],project:{production_request:{status:'done'}},plan:{frames:[{number:3},{number:5}]}};
  const c=vm.createContext({state,sceneGroups:()=>groups,universalClips:()=>[{id:'c3',title:'Razgon · кадр 003'},{id:'c5',title:'Razgon · кадр 005'}],
    clearTransitionSelection(){},renderTimeline(){},renderInspector(){}});
  vm.runInContext(source.slice(source.indexOf('function selectTimelineIds('),source.indexOf('function selectEntireTimeline(')),c);
  c.selectTimelineIds(['c5'],true);
  assert.deepEqual(Array.from(c.selectedRepairFrames()),[3,5]);
});

test('sending frame edits includes exact selected IDs and preserves local montage and playhead',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../groups.js'),'utf8');
  const tracks=[{id:'local'}],state={project:{id:'p',tracks,production:{plan_ready:true}},playhead:140};
  let actions,body;const calls=[],button={disabled:false},field={value:'Move the text above the box'};
  const c=vm.createContext({state,crypto:{randomUUID:()=> 'client-uuid'},modal:(title,html,a)=>{body=html;actions=a;},
    $:id=>id==='frame-repair-notes'?field:{querySelector:()=>button},document:{querySelector:()=>({textContent:''})},
    api:async(...args)=>{calls.push(args);return {project:{tracks:[{id:'remote'}],production_request:{status:'requested'}}};},
    closeModal(){},renderGroupingControls(){},renderMontageMake(){},status(){}});
  vm.runInContext(source.slice(source.indexOf('function openFrameRepair('),source.indexOf('function selectEntireTimeline(')),c);
  c.openFrameRepair([3,5]);await actions[0].run();
  assert.match(body,/Кадр 3/);assert.match(body,/Кадр 5/);
  assert.equal(calls[0][0],'/api/projects/p/production-edits');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])),{notes:field.value,frame_numbers:[3,5],client_id:'client-uuid'});
  assert.equal(state.project.tracks,tracks);assert.equal(state.playhead,140);assert.equal(state.project.production.plan_ready,true);
});
