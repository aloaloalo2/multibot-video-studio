const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../ui-controls.js'),'utf8')+'\nglobalThis.ui=StudioUI;';
test('UI preferences are validated and unavailable storage never blocks a control',()=>{
  const values=new Map(),c=vm.createContext({localStorage:{getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)}});vm.runInContext(source,c);
  c.ui.remember('writer:c','trending');assert.equal(c.ui.preference('writer:c',['claude','trending'],'claude'),'trending');
  assert.equal(c.ui.preference('writer:other',['claude','trending'],'claude'),'claude');
  c.localStorage.getItem=()=>{throw Error('private mode');};c.localStorage.setItem=()=>{throw Error('private mode');};
  assert.doesNotThrow(()=>c.ui.remember('writer:c','claude'));assert.equal(c.ui.preference('writer:c',['claude'],'claude'),'claude');
});
test('segmented controls support keyboard selection once after repeated enhancement',()=>{
  let listeners=0,handler,clicked=null;const buttons=[0,1,2].map(number=>({disabled:false,focus(){},click(){clicked=number;}}));
  buttons[1].disabled=true;const group={classList:{add(){}},querySelectorAll:()=>buttons,addEventListener:(event,callback)=>{listeners++;handler=callback;}};
  const c=vm.createContext({});vm.runInContext(source,c);const root={querySelectorAll:selector=>selector.startsWith('button')?[]:[group]};
  c.ui.enhance(root);c.ui.enhance(root);assert.equal(listeners,1);
  handler({key:'ArrowRight',target:buttons[0],preventDefault(){}});assert.equal(clicked,2);
});
