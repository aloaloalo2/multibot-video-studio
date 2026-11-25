const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=file=>fs.readFileSync(path.join(__dirname,'..',file),'utf8');

// a tiny element: enough for the waveform and selection code
function element(tag='div'){
  const node={tagName:tag,children:[],parentNode:null,attrs:{},dataset:{},classes:new Set(),
    get isConnected(){let n=this;while(n.parentNode)n=n.parentNode;return n.root===true;},
    get firstChild(){return this.children[0];},
    classList:{add:(...c)=>c.forEach(x=>node.classes.add(x)),remove:(...c)=>c.forEach(x=>node.classes.delete(x)),contains:c=>node.classes.has(c),
      toggle:(c,on)=>{on=on===undefined?!node.classes.has(c):!!on;on?node.classes.add(c):node.classes.delete(c);return on;}},
    setAttribute(k,v){this.attrs[k]=String(v);},
    append(...kids){for(const k of kids){k.parentNode?.children.splice(k.parentNode.children.indexOf(k),1);k.parentNode=this;this.children.push(k);}},
    prepend(k){k.parentNode?.children.splice(k.parentNode.children.indexOf(k),1);k.parentNode=this;this.children.unshift(k);},
    remove(){if(this.parentNode){this.parentNode.children.splice(this.parentNode.children.indexOf(this),1);this.parentNode=null;}},
    querySelector(sel){const cls=sel.replace('.','');const walk=n=>{for(const k of n.children){if(k.classes.has(cls))return k;const f=walk(k);if(f)return f;}return null;};return walk(this);},
    cloneNode(){const copy=element(this.tagName);copy.attrs={...this.attrs};this.classes.forEach(c=>copy.classes.add(c));for(const k of this.children)copy.append(k.cloneNode(true));return copy;}};
  return node;
}

test('a sound clip outline is built once, moved into the next redraw and copied for a second clip of the same sound',async()=>{
  const c=vm.createContext({state:{project:{id:'p'}},timelineSpan:()=>100,timelineWidth:()=>1000,fetch:()=>assert.fail('read once'),
    document:{createElementNS:(_,tag)=>element(tag)},queueMicrotask});
  vm.runInContext(read('waveforms.js'),c);
  const url='/api/projects/p/assets/a/waveform';
  vm.runInContext('waveformData',c).set(url,{duration:10,peaks:Array.from({length:800},(_,i)=>[-(i%7)/10,(i%5)/10])});
  const clip={asset_id:'a',duration:2,trim_start:1};
  let built=0;const path=c.waveformPath;c.waveformPath=(...args)=>{built++;return path(...args);};
  const a=element('button'),b=element('button');
  c.drawAudioWaveform(a,clip);c.drawAudioWaveform(b,clip);
  const first=a.querySelector('.audio-waveform'),second=b.querySelector('.audio-waveform');
  assert.ok(first&&second);assert.notEqual(first,second);assert.equal(first.firstChild.attrs.d,second.firstChild.attrs.d);
  await new Promise(resolve=>setImmediate(resolve));   // the next redraw
  const again=element('button');c.drawAudioWaveform(again,clip);
  assert.equal(again.querySelector('.audio-waveform'),first);assert.equal(built,1);
  assert.equal(c.waveformPoints(clip),64);   // 20 px: 40 points, up to the next power of two
});

test('a waveform keeps two points a pixel, in steps of a power of two',()=>{
  const c=vm.createContext({state:{project:{id:'p'}},timelineSpan:()=>100,timelineWidth:()=>1000});
  vm.runInContext(read('waveforms.js'),c);
  assert.equal(c.waveformPoints({duration:.1}),16);
  assert.equal(c.waveformPoints({duration:10}),256);   // 100 px
  assert.equal(c.waveformPoints({duration:1000}),4096);
});

test('a selection marks the drawn blocks without drawing the timeline again',()=>{
  const clips=['c1','c2','c3'].map(id=>{const n=element('button');n.dataset.clipId=id;return n;});
  const group=element('button');group.dataset.groupId='g';
  const lane=element('div');lane.dataset.layerId='L';const row=element('div');row.append(lane);lane.closest=()=>row;
  const state={selected:'c1',multiSelection:['c2','c3'],selectedGroup:null,activeLayer:'L'};
  const source=read('groups.js');let controls=0;
  const c=vm.createContext({state,renderGroupingControls:()=>controls++,memoForProject:(_,f)=>f(),sceneGroups:()=>[{id:'g',clip_ids:['c2','c3']}],
    document:{querySelectorAll:sel=>sel.includes('.track-row')?[row]:sel.includes('data-clip-id')?clips:sel.includes('data-group-id')?[group]:sel.includes('data-layer-id')?[lane]:[]}});
  vm.runInContext(source.slice(source.indexOf('function groupById('),source.indexOf('function closeStackMenu(')),c);
  vm.runInContext(source.slice(source.indexOf('function refreshTimelineSelection('),source.indexOf('function expandFrameGroup(')),c);
  assert.equal(c.refreshTimelineSelection(),true);
  assert.deepEqual(clips.map(n=>[n.classes.has('selected'),n.classes.has('multi-selected')]),[[true,false],[false,true],[false,true]]);
  assert.equal(group.classes.has('selected'),true);assert.equal(row.classes.has('active-layer'),true);assert.equal(controls,1);
  state.multiSelection=['c2'];state.selected=null;state.activeLayer=null;c.refreshTimelineSelection();
  assert.equal(group.classes.has('selected'),false);assert.equal(clips[0].classes.has('selected'),false);assert.equal(row.classes.has('active-layer'),false);
});

test('a seam reads the first transition saved for its two sides',()=>{
  const source=read('transitions.js'),first={id:'a',from_ref:'group:1',to_ref:'group:2'},later={id:'b',from_ref:'group:1',to_ref:'group:2'};
  const c=vm.createContext({state:{project:{join_transitions:[first,later,{id:'c',from_ref:'group:2',to_ref:'group:3'}]}},memoForProject:(_,f)=>f()});
  vm.runInContext(source.slice(source.indexOf('function joinAt('),source.indexOf('function transitionJoinMarker(')),c);
  assert.equal(c.joinAt('group:1','group:2'),first);assert.equal(c.joinAt('group:2','group:3').id,'c');assert.equal(c.joinAt('group:3','group:4'),undefined);
});
