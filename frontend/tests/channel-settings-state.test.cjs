const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../channel-settings.js'),'utf8'),context);
const field=(value,type='text')=>({value,type,isConnected:true,checked:false,matches:()=>false,closest:()=>null});

test('opening loaded settings is clean; editing and reverting returns to a clean draft',()=>{
  const name=field('Channel'),speed=field('100','range'),baseline=new Map([[name,'Channel'],[speed,'100']]);
  assert.equal(context.channelSettingsDirty(baseline),false);
  speed.value='95';assert.equal(context.channelSettingsDirty(baseline),true);
  speed.value='100';assert.equal(context.channelSettingsDirty(baseline),false);
  name.value='Other';assert.equal(context.channelSettingsDirty(baseline),true);
});

test('toggle and style changes are tracked, while detached async controls do not keep Save active',()=>{
  const toggle=field('on','checkbox');toggle.checked=true;
  const style=field('dusk','hidden');
  const baseline=new Map([[toggle,'true'],[style,'dusk']]);
  toggle.checked=false;assert.equal(context.channelSettingsDirty(baseline),true);
  toggle.checked=true;style.value='clinic';assert.equal(context.channelSettingsDirty(baseline),true);
  style.value='dusk';assert.equal(context.channelSettingsDirty(baseline),false);
  style.value='old';style.isConnected=false;assert.equal(context.channelSettingsDirty(baseline),false);
});

test('radio button state is compared by selection rather than its unchanged value',()=>{
  let state='false';const button={isConnected:true,matches:()=>true,closest:()=>null,getAttribute:()=>state};
  const baseline=new Map([[button,'false']]);
  assert.equal(context.channelSettingsDirty(baseline),false);
  state='true';assert.equal(context.channelSettingsDirty(baseline),true);
});

// Translation reference players arrive after the main form. Their volume slider has no output sibling.
test('async audio player sliders neither throw during reset setup nor dirty channel settings',()=>{
  const volume={...field('.8','range'),nextElementSibling:null,closest:()=>({})};
  const seek={...field('0','range'),nextElementSibling:{matches:()=>false},closest:()=>({})};
  assert.equal(context.channelSettingsResetAnchor(volume),null);
  assert.equal(context.channelSettingsResetAnchor(seek),null);
  volume.value='.2';seek.value='22';
  const wishes=field('New preview wishes');
  const baseline=new Map([[volume,'.8'],[seek,'0'],[wishes,'Old wishes']]);
  assert.equal(context.channelSettingsDirty(baseline),true);
  wishes.value='Old wishes';assert.equal(context.channelSettingsDirty(baseline),false);
  const output={matches:selector=>selector==='output'};
  assert.equal(context.channelSettingsResetAnchor({...field('90','range'),nextElementSibling:output}),output);
  assert.equal(context.channelSettingsResetAnchor({...field('90','range'),nextElementSibling:null}),null);
});
