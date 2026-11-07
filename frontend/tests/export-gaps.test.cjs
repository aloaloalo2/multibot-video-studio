const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','universal.js'),'utf8');
const fn=source.slice(source.indexOf('function visualGaps()'),source.indexOf('function renderTimelineGaps()'));

const transitions=fs.readFileSync(path.join(__dirname,'..','transitions.js'),'utf8');
const bounds=transitions.slice(transitions.indexOf('function transitionEndpoint('),transitions.indexOf('function transitionValues('));
function gaps(length,clips,fps=25,joins=[],groups=[]){
  const items=clips.map(([start,end],i)=>({id:'c'+i,kind:'image',start,duration:end-start}));
  const context=vm.createContext({state:{project:{id:'test',revision:1,fps,join_transitions:joins}},memoForProject:(_,f)=>f(),isUniversal:()=>true,
    sceneGroups:()=>groups,groupMembers:g=>items.filter(c=>g.clip_ids.includes(c.id)),universalClips:()=>items,
    duration:()=>length});
  vm.runInContext('let joinCacheToken,joinCache;',context);
  vm.runInContext(bounds,context);
  vm.runInContext(fn,context);
  return JSON.parse(JSON.stringify(vm.runInContext('visualGaps()',context)));
}

test('Billionaire fractional final audio sample does not show a false empty-screen warning',()=>{
  assert.deepEqual(gaps(3223.3,[[0,3223.28]]),[]);
});
test('fractional end uses the same output-frame coverage as the renderer',()=>{
  assert.deepEqual(gaps(1.005,[[0,1.005]]),[]);
  assert.deepEqual(gaps(1.005,[[0,1]]),[]);
  assert.deepEqual(gaps(1.001,[[0,1]],30),[]);
});
test('real tail gaps longer than a frame remain visible',()=>{
  assert.deepEqual(gaps(1.5,[[0,1]]),[{start:1,end:1.52}]);
});
test('even a one-frame interior gap remains visible',()=>{
  assert.deepEqual(gaps(2,[[0,1],[1.04,2]]),[{start:1,end:1.04}]);
});

test('outgoing transition coverage is counted for a scene group at output-frame boundaries',()=>{
  const groups=[{id:'a',role:'scene',clip_ids:['c0']},{id:'b',role:'scene',clip_ids:['c1']}];
  const joins=[{from_ref:'group:a',to_ref:'group:b',seam:1,duration:.35,type:'crossfade'}];
  assert.deepEqual(gaps(2,[[0,1],[1.36,2]],25,joins,groups),[]);
  assert.deepEqual(gaps(2,[[0,1],[1.4,2]],25,joins,groups),[{start:1.36,end:1.4}]);
});
test('a transition extends only its actual outgoing endpoint',()=>{
  const joins=[{from_ref:'clip:c0',to_ref:'clip:c1',seam:1,duration:.35,type:'slide_left'}];
  assert.deepEqual(gaps(3,[[0,1],[1.36,2],[2.2,3]],25,joins),[{start:2,end:2.2}]);
});
