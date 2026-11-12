const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../script-editing.js'),'utf8');
function setup(){const c=vm.createContext({esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')});vm.runInContext(source,c);return c;}
test('word-level changes escape source and mark only replaced spans',()=>{
 const c=setup(),tokens=[{text:'Same ',changed:false},{text:'<script>bad</script>',changed:true}];
 assert.equal(c.scriptEditingTokens(tokens,'before'),'Same <del>&lt;script&gt;bad&lt;/script&gt;</del>');
 assert.equal(c.scriptEditingTokens(tokens,'after'),'Same <ins>&lt;script&gt;bad&lt;/script&gt;</ins>');
});
test('comparison loads lazily, preserves project ownership, and never starts inference on opening',async()=>{
 let calls=[];const root={isConnected:true,innerHTML:''},state={project:{id:'p'},navigation:1,modalGeneration:1};
 const c=vm.createContext({state,esc:String,modal(){},$:()=>({querySelector:()=>root}),api:async(...a)=>{calls.push(a);return {available:false};}});vm.runInContext(source,c);
 await c.openScriptEditing({id:'p'});assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/projects/p/script-editing');assert.equal(calls[0].length,1);assert.match(root.innerHTML,/Готові попередні/);
});
test('late report cannot replace another project',async()=>{
 let resolve;const root={isConnected:true,innerHTML:'original'},state={project:{id:'p'},navigation:1,modalGeneration:1};
 const c=vm.createContext({state,esc:String,modal(){},$:()=>({querySelector:()=>root}),api:()=>new Promise(r=>resolve=r)});vm.runInContext(source,c);
 const pending=c.openScriptEditing({id:'p'});state.project={id:'other'};resolve({available:false});await pending;assert.equal(root.innerHTML,'original');
});

test('editor button uses an icon, stays disabled without a report, and enables only for its project',async()=>{
 for(const available of [false,true]){
  const button={isConnected:true,setAttribute(name,value){this[name]=value;}};
  const c=vm.createContext({document:{createElement:()=>button},state:{project:{id:'p'}},api:async()=>({available}),esc:String});vm.runInContext(source,c);
  c.createScriptEditingButton({id:'p'});assert.equal(button.disabled,true);assert.match(button.innerHTML,/<svg/);
  await Promise.resolve();await Promise.resolve();assert.equal(button.disabled,!available);
  assert.match(button.title,available?/Редактура/:/ще немає/);
 }
 let resolve;const button={isConnected:true,setAttribute(){}};const state={project:{id:'p'}};
 const c=vm.createContext({document:{createElement:()=>button},state,api:()=>new Promise(r=>resolve=r),esc:String});vm.runInContext(source,c);
 c.createScriptEditingButton({id:'p'});state.project={id:'other'};resolve({available:true});await Promise.resolve();await Promise.resolve();assert.equal(button.disabled,true);
});

test('author cost is approximate subscription allocation with raw API equivalent retained',()=>{
 const c=setup();assert.equal(c.scriptEditingCost({provider:'claude_code',cost_usd:.7}),'≈$0.020000 (API $0.700000)');
 assert.equal(c.scriptEditingCost({provider:'openrouter',cost_usd:.003}),'$0.003000');
});
test('subjective assessments stay separate and escape report content',()=>{
 const c=setup();const html=c.scriptEditingAssessment({before_scores:{clarity:{score:5,reason:'<unsafe>'}},after_scores:{clarity:{score:7,reason:'Clearer'}},changes:[{before:'<script>',after:'Safe',reason:'Natural',comparison_verified:false}],unresolved:[{location:'First paragraph',issue:'Unverified claim',needs_fact_check:true}]});
 assert.match(html,/Суб’єктивна самооцінка/);assert.match(html,/&lt;unsafe&gt;/);assert.match(html,/Цитати потребують звірки/);assert.match(html,/Потрібна перевірка фактів/);assert.doesNotMatch(html,/<script>/);
});

test('three editorial assessments and actual refinement are distinct in the report',()=>{
 const c=setup();const scores={clarity:{score:7,reason:'Concrete reason'}};
 const html=c.scriptEditingAssessment({before_scores:scores,intermediate_scores:scores,after_scores:scores});
 assert.match(html,/Чернетка/);assert.match(html,/Після основної редактури/);assert.match(html,/Фінал/);
 const refinement=c.scriptEditingRefinement({summary:'Removed an empty sentence',remaining_weaknesses:[{location:'Last line',problem:'Empty rhetoric'}],actions:[{before:'Empty rhetoric.',after:'',reason:'No useful information'}]});
 assert.match(refinement,/Залишкові слабкі місця/);assert.match(refinement,/Цільові правки до фіналу/);
 const receipt=c.scriptEditingReceiptRows({requests:[{phase:'main',provider:'claude_code',request_id:'one',cost_usd:.2,usage:{input_tokens:5,cache_read_input_tokens:20,output_tokens:10}}]});
 assert.match(receipt,/Основний слоп-чек/);assert.match(receipt,/25 \/ 10/);assert.doesNotMatch(receipt,/NaN/);assert.match(receipt,/API \$0.200000/);
});
