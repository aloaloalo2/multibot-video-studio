const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
function fixture(){
 const badge={setAttribute(key,value){this[key]=value;}},storage={};
 const context={state:{view:'editor',channel:null},channelActivity:new Set(),document:{querySelectorAll:()=>[{dataset:{channelId:'one'},querySelector:()=>badge}]},StudioUI:{icon:name=>`<svg>${name}</svg>`},localStorage:{getItem:()=>null,setItem:(key,value)=>storage[key]=value}};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('const channelNoticeStorage='),source.indexOf('let channelActivityPending=')),context);
 return {context,badge,storage,run:code=>vm.runInContext(code,context)};
}
test('spinner becomes a check or stop in the same slot and explicit click acknowledges it',()=>{
 const f=fixture();f.run("channelNoticeData.one={id:'1',status:'done'};renderChannelNotices()");
 assert.match(f.badge.className,/is-complete/);assert.match(f.badge.innerHTML,/check/);assert.equal(f.badge.hidden,false);
 f.context.channelActivity.add('one');f.context.renderChannelNotices();assert.equal(f.badge.innerHTML,'');assert.equal(f.badge.className,'channel-busy');
 f.context.channelActivity.clear();f.run("channelNoticeData.one={id:'2',status:'stopped'};renderChannelNotices()");
 assert.match(f.badge.className,/is-stopped/);f.context.acknowledgeChannelNotice('one');assert.equal(f.badge.hidden,true);
 f.context.renderChannelNotices();assert.equal(f.badge.hidden,true);
 f.run("channelNoticeData.one={id:'3',status:'done',seen:'2'};renderChannelNotices()");assert.equal(f.badge.hidden,false);
});
test('automatic sidebar renders preserve an unread notice and no notice stays hidden',()=>{
 const f=fixture();f.context.renderChannelNotices();assert.equal(f.badge.hidden,true);
 f.run("channelNoticeData.one={id:'1',status:'done'};renderChannelNotices();renderChannelNotices()");assert.equal(f.badge.hidden,false);
});

test('the open channel consumes completion silently while its running spinner remains visible',()=>{
 const f=fixture();f.context.state.channel={id:'one'};
 f.context.channelActivity.add('one');f.context.renderChannelNotices();assert.equal(f.badge.hidden,false);
 f.context.channelActivity.clear();
 for(const status of ['done','stopped']){
  f.run(`channelNoticeData.one={id:'${status}',status:'${status}'};renderChannelNotices()`);
  assert.equal(f.badge.hidden,true);assert.match(Object.values(f.storage)[0],new RegExp('"seen":"'+status+'"'));
 }
 f.context.state.channel={id:'other'};f.context.renderChannelNotices();assert.equal(f.badge.hidden,true);
});
test('a selected channel keeps unseen notifications while the trends page is open',()=>{
 const f=fixture();f.context.state.channel={id:'one'};f.context.state.view='trends';
 f.run("channelNoticeData.one={id:'done',status:'done'};renderChannelNotices()");assert.equal(f.badge.hidden,false);
});
