const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../trending-videos.js'),'utf8');
const context=vm.createContext({Intl,Date,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))});
vm.runInContext(source.slice(0,source.indexOf('function openTrendingVideos')),context);
const video={id:'abcdefghijk',title:'What If You Aged Backwards?',published_at:'2026-11-10',views:24000,score:3,duration:500,competitor_id:'UC'+'a'.repeat(22),competitor_name:'Competitor',subscribers:5000,for_channels:[{name:'Our channel'}]};
test('cards preserve the source title and show a readable Ukrainian subtitle',()=>{
  const html=context.trendingCard({...video,title_uk:'Що було б, якби ви молодшали?'});
  assert.ok(html.includes(video.title));
  assert.match(html,/<p class="trend-title-uk" lang="uk" title="Що було б, якби ви молодшали\?">Що було б, якби ви молодшали\?<\/p>/);
});
test('missing translations add no empty label and provider text is escaped',()=>{
  assert.ok(!context.trendingCard(video).includes('trend-title-uk'));
  const html=context.trendingCard({...video,title_uk:'<img src=x onerror="alert(1)">'});
  assert.ok(html.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'));
  assert.ok(!html.includes('<img src=x'));
});
