const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../project-costs.js'),'utf8');
test('concurrent hovers share one read and reuse the cached cost summary',async()=>{
  let calls=0;const c=vm.createContext({api:async()=>{calls++;return {providers:{}};}});vm.runInContext(source,c);
  await vm.runInContext("Promise.all([loadProjectCosts('p'),loadProjectCosts('p')])",c);
  await vm.runInContext("loadProjectCosts('p')",c);assert.equal(calls,1);
});
test('provider badges distinguish estimated dollars and unknown costs',()=>{
  const c=vm.createContext({esc:s=>s});vm.runInContext(source,c);
  const html=vm.runInContext("projectCostMarkup({providers:{openrouter:{usd:.1},claude_code:{usd:20,equivalent:true},elevenlabs:{usd:null,estimated:true}}})",c);
  assert.match(html,/OpenRouter: \$0.10/);assert.match(html,/Claude Code: ≈ \$0.69/);assert.match(html,/ElevenLabs: ≈ \$…/);
  assert.match(html,/API-еквівалент \$20.00 ÷ 29/);
});
