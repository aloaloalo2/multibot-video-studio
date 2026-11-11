const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8'),universal=fs.readFileSync(path.join(__dirname,'../universal.js'),'utf8');
test('transition toolbar opens the real media library and keeps tab controls synchronized',()=>{
  const state={libraryTab:'pixabay'},kind={hidden:false};let assets=0,timeline=0,searches=0;
  const tabs=['local','pixabay','transitions'].map(tab=>({dataset:{tab},classList:{toggle(key,value){this[key]=value}},setAttribute(key,value){this[key]=value}}));
  const c=vm.createContext({state,$:()=>kind,document:{querySelectorAll:()=>tabs},renderAssets:()=>assets++,renderTimeline:()=>timeline++,searchPixabay:()=>searches++,status(){}});
  const start=app.indexOf('function selectLibraryTab(');
  vm.runInContext(app.slice(start,app.indexOf('\ndocument.querySelectorAll',start)),c);
  const transition=universal.indexOf('function openUniversalTransition(');
  vm.runInContext(universal.slice(transition,universal.indexOf('\n',transition)),c);
  c.openUniversalTransition();
  assert.equal(state.libraryTab,'transitions');assert.equal(assets,1);assert.equal(timeline,1);assert.equal(searches,0);assert.equal(kind.hidden,true);
  assert.equal(tabs[2]['aria-selected'],'true');assert.equal(tabs[1]['aria-selected'],'false');
  c.selectLibraryTab('pixabay');assert.equal(kind.hidden,false);assert.equal(searches,1);
});
