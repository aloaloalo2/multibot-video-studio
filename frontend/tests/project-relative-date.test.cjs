const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function projectCreationDate('),source.indexOf('function completionMark(')),context);
const format=(created,now)=>context.projectCreationDate(Date.parse(created)/1000,new Date(now));

test('dates follow Kyiv calendar midnight instead of elapsed 24 hours',()=>{
  const today=format('2026-11-09T22:30:00Z','2026-11-10T12:00:00Z');
  assert.equal(today.text,'Сьогодні');
  assert.match(today.fullDate,/10 листопада 2026/);
  assert.equal(format('2026-11-09T21:30:00Z','2026-11-09T22:01:00Z').text,'1 день тому');
});
test('daylight saving does not change the displayed calendar day count',()=>{
  assert.equal(format('2026-03-28T22:30:00Z','2026-03-29T21:30:00Z').text,'1 день тому');
});
test('relative dates use Ukrainian day plurals without years or times',()=>{
  for(const [days,expected] of [[1,'1 день тому'],[2,'2 дні тому'],[5,'5 днів тому'],[11,'11 днів тому'],[21,'21 день тому'],[22,'22 дні тому']]){
    const now=new Date('2026-11-10T12:00:00Z');
    assert.equal(context.projectCreationDate((now.getTime()-days*86400000)/1000,now).text,expected);
  }
});
test('seconds and milliseconds retain exact machine-readable dates; invalid dates stay unknown',()=>{
  const stamp=Date.parse('2026-11-09T12:00:00Z'),now=new Date('2026-11-10T12:00:00Z');
  assert.equal(context.projectCreationDate(stamp,now).datetime,'2026-11-09T12:00:00.000Z');
  assert.equal(context.projectCreationDate(stamp/1000,now).text,'1 день тому');
  for(const value of [null,0,'',NaN,Infinity,'invalid'])assert.equal(context.projectCreationDate(value,now),null);
});
