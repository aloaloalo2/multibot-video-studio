const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const engine=path.resolve(__dirname,'../../razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/engine');
const ui=fs.readFileSync(path.join(engine,'ui2d.js'),'utf8');
const core=()=>import(pathToFileURL(path.join(engine,'core.js')).href);

test('light palette labels meet contrast without changing already readable colors',async()=>{
  const {readableTextColor,textContrast}=await core();
  for(const color of ['#f2b632','#3fb489','#8fb8e8','#d94f4f'])
    assert.ok(textContrast(readableTextColor(color,'#fbfffd'),'#fbfffd')>=4.5);
  assert.equal(readableTextColor('#21393d','#fbfffd'),'#21393d');
});
test('labels fade in at a fixed anchor and do not add a light halo',async()=>{
  const {readableTextColor,luma}=await core(),calls=[];
  const context=vm.createContext({E:{W:1920},S:()=>({ui:{card:'#fbfffd',gold:'#f2b632'}}),V:x=>x,clamp:x=>Math.max(0,Math.min(1,x)),FONTS:{ui:'Noto Serif'},readableTextColor,luma,text:(...args)=>calls.push(args)});
  vm.runInContext(ui.slice(ui.indexOf('export function label('),ui.indexOf('// Glowing single question')).replace('export ',''),context);
  const g={globalAlpha:1,save(){},restore(){}};
  context.label(g,'инсулин высокий',300,200,.4);
  context.label(g,'инсулин высокий',300,200,1);
  assert.equal(calls[0][3],200);assert.equal(calls[1][3],200);
  assert.equal(calls[0][4].shadow.length,0);
});
test('heading layout stays fixed while its opacity changes',async()=>{
  const headings=[];
  const context=vm.createContext({E:{W:1920,H:1080},S:()=>({ui:{gold:'#ffd47e',cream:'#fff',accent:'#f00'}}),fadeIO:()=>1,V:x=>x,measure:(_,s,size)=>s.length*size/2,text:(_,s,x,y)=>headings.push([s,x,y]),alpha:x=>x});
  vm.runInContext(ui.slice(ui.indexOf('export function titleCard('),ui.indexOf('export function label(')).replace('export ',''),context);
  const g={globalAlpha:1,save(){},restore(){},translate(){},scale(){assert.fail('Heading continuously zoomed');},fillRect(){}};
  context.titleCard(g,1,{lines:['A heading']});context.titleCard(g,3,{lines:['A heading']});
  assert.deepEqual(headings[0],headings[1]);
});
