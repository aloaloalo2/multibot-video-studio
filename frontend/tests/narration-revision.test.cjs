const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../narration-revision.js'),'utf8'),context);
test('completed phrase count switches to assembly instead of implying synthesis is stuck',()=>{
 assert.equal(context.narrationRevisionStage({status:'running',completed:1,total:1}),'Збираємо оновлену озвучку');
 assert.equal(context.narrationRevisionStage({status:'running',stage:'saving',completed:1,total:1}),'Зберігаємо зміни');
 assert.equal(context.narrationRevisionStage({status:'queued'}),'У черзі на переозвучення');
 assert.equal(context.narrationRevisionStage({status:'running',stage:'synthesizing',completed:0,total:1}),'Переозвучуємо речення 1 з 1');
 assert.equal(context.narrationRevisionStage({status:'cancelling'}),'Зупиняємо переозвучення');
});
test('working state includes the shared animated spinner with accessible status text',()=>{
 const element={classList:{add(value){element.className=value;}},replaceChildren(){this.children=[];},append(...children){this.children=children;}};
 context.document={createElement(){return {setAttribute(key,value){this[key]=value;}};}};
 context.showNarrationRevisionStage(element,{stage:'assembling'});
 assert.equal(element.className,'is-working');assert.equal(element.children[0].className,'export-spinner');
 assert.equal(element.children[0]['aria-hidden'],'true');assert.equal(element.children[1].textContent,'Збираємо оновлену озвучку');
});
