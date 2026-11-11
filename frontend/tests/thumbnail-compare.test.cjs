const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const c=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../thumbnail-compare.js'),'utf8'),c);
test('an edited result uses its exact base in the same language',()=>{
  const before={key:'original-v1',code:'original',base:'v1.png',url:'/original'},foreign={key:'es-v1',code:'es',base:'v1.png',url:'/es'};
  const edited={key:'es-v2',code:'es',base:'v2.png',comparison:{kind:'edit',base:'v1.png'}};
  const value=c.thumbnailComparison(edited,[before,foreign,edited],{});assert.equal(value.url,'/es');assert.equal(value.after,'Після правок');
  assert.equal(c.thumbnailComparison(edited,[before,edited],{}),null);
});
test('a clone version keeps its original reference when the episode source changes',()=>{
  const item={code:'original',base:'v1.png',comparison:{kind:'clone',url:'/immutable-first'}};
  assert.equal(c.thumbnailComparison(item,[],{clone_reference:{thumbnail_url:'/different'}}).url,'/immutable-first');
});
test('legacy comparison is shown only for a matching completed job and reference',()=>{
  const item={code:'original',base:'v1.png'},data={job:{file:'v1.png',reference_id:'one'},clone_reference:{id:'one',thumbnail_url:'/reference'}};
  assert.equal(c.thumbnailComparison(item,[],data).url,'/reference');data.job.reference_id='another';assert.equal(c.thumbnailComparison(item,[],data),null);
});
