// New transitions start the polling again after it stopped (27 November 2026: «чому синє… але нема переходу»).
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'capcut.js'), 'utf8');
const start = source.indexOf('let capcutDrawn=');
const end = source.indexOf('\n}\n', source.indexOf('async function refreshCapcutReady')) + 3;
const timers = [];
const context = {
  state: {project: {id: 'p', join_transitions: []}, playing: false},
  ready: [], calls: 0,
  isCapcutTransition: (type) => String(type).startsWith('capcut_'),
  capcutJoinKey: (join) => join.id, capcutPreviews: new Map(), capcutWaiting: new Set(),
  renderPreview() {}, document: {querySelectorAll: () => []},
  setTimeout: (fn) => { timers.push(fn); return timers.length; }, clearTimeout() {},
};
context.api = async () => { context.calls += 1; return {ready: context.ready, urls: {}}; };
vm.createContext(context);
vm.runInContext(source.slice(start, end) + '\nthis.refresh = refreshCapcutReady; this.timer = () => capcutReadyTimer;', context);

(async () => {
  context.state.project.join_transitions = [{id: 'j1', type: 'capcut_t08'}];
  await context.refresh();                       // j1 still drawing: the next check is scheduled
  assert.notStrictEqual(context.timer(), 0);
  context.ready = ['j1'];
  await timers.at(-1)();                         // j1 ready: the polling stops
  assert.strictEqual(context.timer(), 0, 'a stopped polling leaves no stale timer id behind');
  context.state.project.join_transitions.push({id: 'j2', type: 'capcut_t38'});   // the frame agent adds a seam
  await context.refresh();                       // app.js restarts it because the timer is 0
  assert.notStrictEqual(context.timer(), 0, 'the new pending transition is checked again');
  assert.strictEqual(context.calls, 3);
  console.log('capcut ready polling ok');
})().catch((error) => { console.error(error); process.exit(1); });
