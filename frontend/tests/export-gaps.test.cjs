const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','universal.js'),'utf8');
const fn=source.slice(source.indexOf('function visualGaps()'),source.indexOf('function renderTimelineGaps()'));

function gaps(length,clips,fps=25){
  const context=vm.createContext({state:{project:{fps}},memoForProject:(_,f)=>f(),isUniversal:()=>true,
    sceneGroups:()=>[],universalClips:()=>clips.map(([start,end])=>({kind:'image',start,duration:end-start})),
    duration:()=>length});
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
