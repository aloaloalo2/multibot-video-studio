const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context=vm.createContext({URL});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../channel-competitors.js'),'utf8'),context);
test('handles are readable without expanding the saved encoded address',()=>{
  const source='https://www.youtube.com/@'+encodeURIComponent('КосмическийСтранник');
  const item={source_url:source,url:'https://www.youtube.com/channel/UC'+'a'.repeat(22)};
  const address=context.competitorAddress(item);
  assert.equal(address.label,'@КосмическийСтранник');assert.equal(address.title,'https://www.youtube.com/@КосмическийСтранник');
  assert.equal(item.source_url,source);
});
test('custom and user channel paths remain accurate and omit protocol and query noise',()=>{
  for(const prefix of ['c','user']){
    const address=context.competitorAddress({source_url:`https://www.youtube.com/${prefix}/channelName/?feature=shared`});
    assert.equal(address.label,`${prefix}/channelName`);assert.match(address.title,/feature=shared/);
  }
});
test('canonical IDs and malformed addresses have a compact safe fallback',()=>{
  for(const source of ['https://www.youtube.com/channel/UC'+'a'.repeat(22),'https://www.youtube.com/@broken%E0%A4%A','invalid','https://example.test/channel']){
    assert.equal(context.competitorAddress({url:source}).label,'YouTube');
  }
});
