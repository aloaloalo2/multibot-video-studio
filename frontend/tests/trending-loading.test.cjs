const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../trending-videos.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const feed=(extra={})=>({videos:[{id:'abcdefghijk',title:'Title',published_at:'2026-11-12',views:5000,score:2,duration:600,for_channels:[],competitor_id:'C',competitor_name:'C',subscribers:100}],channels:[],competitor_icons:{},running:false,errors:[],warnings:[],competitors:1,checked:1,...extra});
function harness(replies){
 const calls=[],timers=new Map(),state={navigation:0},classes=new Set(),attrs={};let nextTimer=0,writes=0;
 const select={value:'',innerHTML:''},button={disabled:false,classList:{toggle:(key,value)=>value?classes.add(key):classes.delete(key)},setAttribute:(key,value)=>attrs[key]=value};
 const feedback={hidden:false,textContent:''},list={innerHTML:''},notices={hidden:true,querySelector:()=>list},toolbar={};
 const grid={get innerHTML(){return this.html||'';},set innerHTML(value){writes++;this.html=value;}};
 const nodes={select,'.trend-refresh':button,'.trend-feedback':feedback,'.trend-notices':notices,'.trend-grid':grid,'.trend-top':toolbar};
 const root={isConnected:true,hidden:false,innerHTML:'',querySelector:selector=>nodes[selector]},slot={replaceChildren:child=>slot.child=child};
 const context=vm.createContext({state,Intl,Date,Set,esc:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),$:id=>id==='trending-page'?root:slot,
  cancelLocationRestore(){},stopPlayback(){},closeModal(){},renderChannels(){},renderProject(){},status(){},syncRoute(){},
  setTimeout:(fn,delay)=>{timers.set(++nextTimer,{fn,delay});return nextTimer;},clearTimeout:id=>timers.delete(id),clearInterval(){},
  api:async(path,method='GET')=>{calls.push({path,method});const answer=replies.shift();if(answer instanceof Error)throw answer;return answer;}});
 vm.runInContext(source.slice(0,source.indexOf("document.getElementById('trending-videos')")),context);
 const h={state,root,slot,toolbar,button,feedback,notices,list,grid,select,classes,attrs,calls,timers,get writes(){return writes;},open:()=>context.openTrendingVideos()};
 h.next=async()=>{assert(timers.size);const [id,timer]=timers.entries().next().value;timers.delete(id);await timer.fn();return timer.delay;};return h;
}
test('running updates keep raw source diagnostics out of the feed and retain unchanged cards',async()=>{
 const data=feed({running:true,warnings:['C: <unavailable>']}),h=harness([data,data]);h.open();await tick();
 assert.equal(h.slot.child,h.toolbar);assert.equal(h.button.disabled,true);assert(h.classes.has('is-loading'));assert.equal(h.attrs['aria-busy'],'true');
 assert.equal(h.feedback.textContent,'Оновлюємо добірку…');assert(!h.root.innerHTML.includes('trend-notices'));assert(!h.root.innerHTML.includes('Деталі оновлення'));
 assert.equal(h.writes,1);await h.next();assert.equal(h.writes,1);assert(h.calls.every(call=>call.method==='GET'));
});
test('a failed initial read retries status without creating a refresh or author request',async()=>{
 const h=harness([new Error('Read failed'),feed()]);h.open();await tick();assert.equal(h.feedback.textContent,'Read failed');
 assert.equal(await h.next(),2000);assert.equal(h.button.disabled,false);assert.equal(h.feedback.hidden,true);assert.equal(h.writes,1);assert.equal(h.timers.size,0);
 assert.deepEqual(h.calls.map(call=>call.method),['GET','GET']);
});
test('failed polling backs off and releases the spinner on a later completed result',async()=>{
 const h=harness([feed({running:true}),new Error('Offline'),new Error('Still offline'),feed()]);h.open();await tick();
 await h.next();assert.equal(h.button.disabled,true);assert.equal(await h.next(),2000);assert.equal(await h.next(),4000);
 assert.equal(h.button.disabled,false);assert.equal(h.attrs['aria-busy'],'false');assert(!h.classes.has('is-loading'));assert.equal(h.feedback.hidden,true);assert.equal(h.timers.size,0);
 assert(h.calls.every(call=>call.method==='GET'));
});
test('a refresh completed before its first status read cannot leave a stale busy label',async()=>{
 const h=harness([feed(),{running:false},feed()]);h.open();await tick();await h.button.onclick();
 assert.equal(h.button.disabled,false);assert.equal(h.feedback.hidden,true);assert(!h.classes.has('is-loading'));assert.equal(h.timers.size,0);
 assert.deepEqual(h.calls.map(call=>call.method),['GET','POST','GET']);
});
test('a read started before manual refresh cannot restore an old running state',async()=>{
 const old=deferred(),h=harness([old.promise,{running:false},feed()]);h.open();await tick();await h.button.onclick();old.resolve(feed({running:true}));await tick();
 assert.equal(h.button.disabled,false);assert.equal(h.feedback.hidden,true);assert.equal(h.timers.size,0);
});
test('leaving the page prevents late errors from restarting its polling',async()=>{
 const old=deferred(),h=harness([old.promise]);h.open();h.state.navigation++;old.resolve(feed({running:true}));await tick();
 assert.equal(h.timers.size,0);assert.equal(h.writes,0);
});
