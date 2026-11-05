const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');
const heading=source.slice(source.indexOf('function projectCardHeading('),source.indexOf('function projectProductionCardState('));

test('project name opens rename independently of the card open button',()=>{
  let renamed,stopped=false;
  const document={createElement:tag=>({tag,children:[],attributes:{},events:{},setAttribute(k,v){this.attributes[k]=v;},
    append(child){this.children.push(child);},addEventListener(k,fn){this.events[k]=fn;}})};
  const c=vm.createContext({document,projectIcon:'icon',renameProject:p=>renamed=p});
  vm.runInContext(heading,c);const h=vm.runInContext("projectCardHeading({id:'p',name:'New title'})",c);
  const button=h.children[0];assert.equal(button.tag,'button');assert.equal(button.textContent,'New title');
  button.events.click({stopPropagation(){stopped=true;}});
  assert.equal(stopped,true);assert.equal(renamed.id,'p');
  assert.match(button.attributes['aria-label'],/Перейменувати/);
});
