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
