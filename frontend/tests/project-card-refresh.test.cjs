const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const cards=fs.readFileSync(path.join(__dirname,'../project-cards.js'),'utf8');
const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
function coverFixture(){
  const classes=new Set(),images=[];let now=0;
  const card={image:null,classList:{add:(...names)=>names.forEach(name=>classes.add(name)),remove:(...names)=>names.forEach(name=>classes.delete(name))},
    querySelector:()=>card.image,append:node=>{card.image=node;}};
  const document={createElement:()=>{
    const image={events:{},naturalWidth:960,decode:async()=>{},addEventListener(name,fn){this.events[name]=fn;},
      replaceWith(node){if(card.image===this)card.image=node;},remove(){if(card.image===this)card.image=null;}};
    images.push(image);return image;
  }};
  const context=vm.createContext({document,Date:{now:()=>now}});vm.runInContext(cards,context);
  const update=project=>context.updateProjectCardCover(card,{id:'p',...project});
  return {card,classes,images,update,advance:ms=>now+=ms};
}
test('status and revision changes keep a mounted preview with the same file version',async()=>{
  const {card,classes,images,update}=coverFixture();
  update({preview_mtime:100,revision:1,updated_at:1});const first=card.image;await first.events.load();
  for(let n=2;n<40;n++)update({preview_mtime:100,revision:n,updated_at:n,production_request:{made:n}});
  assert.equal(images.length,1);assert.equal(card.image,first);assert.ok(classes.has('cover-ready'));
});
test('a changed cover waits for decoding without hiding the previous picture',async()=>{
  const {card,classes,images,update}=coverFixture();
  update({preview_mtime:1});const first=card.image;await first.events.load();
  update({preview_mtime:2});const next=images[1];let finish;
  next.decode=()=>new Promise(resolve=>finish=resolve);const loading=next.events.load();
  assert.equal(card.image,first);assert.ok(classes.has('cover-ready'));
  finish();await loading;
  assert.equal(card.image,next);assert.ok(classes.has('cover-ready'));assert.ok(!classes.has('no-cover'));
});
test('superseded and failed image requests never blank or overwrite the latest cover',async()=>{
  const {card,classes,images,update}=coverFixture();
  update({preview_mtime:1});await card.image.events.load();
  update({preview_mtime:2});const slow=images[1];
  update({preview_mtime:3});const latest=images[2];await latest.events.load();
  await slow.events.load();assert.equal(card.image,latest);
  update({preview_mtime:4});images[3].events.error();
  assert.equal(card.image,latest);assert.ok(classes.has('cover-ready'));assert.ok(classes.has('has-cover'));
  update({});await slow.events.load();assert.equal(card.image,null);assert.ok(classes.has('no-cover'));assert.ok(!classes.has('cover-ready'));
});
test('an initial picture can finish while its failed replacement is pending',async()=>{
  const {card,classes,images,update}=coverFixture();
  update({preview_mtime:1});const first=card.image;
  update({preview_mtime:2});await first.events.load();images[1].events.error();
  assert.equal(card.image,first);assert.ok(classes.has('cover-ready'));
});
test('failed initial and replacement loads restore the placeholder and retry only after the cooldown',async()=>{
  const {card,classes,images,update,advance}=coverFixture();
  update({preview_mtime:1});const first=card.image;
  update({preview_mtime:2});first.events.error();images[1].events.error();
  assert.equal(card.image,null);assert.ok(classes.has('no-cover'));
  update({preview_mtime:2});assert.equal(images.length,2);
  advance(30000);update({preview_mtime:2});assert.equal(images.length,3);
  await images[2].events.load();assert.equal(card.image,images[2]);assert.ok(classes.has('cover-ready'));
});

test('reconciliation keeps unchanged cards in place and handles adding, ordering and deleting projects',()=>{
  const container={children:[],get firstElementChild(){return this.children[0]||null;},insertBefore(node,before){
    const old=this.children.indexOf(node);if(old>=0)this.children.splice(old,1);
    const index=before?this.children.indexOf(before):this.children.length;assert.ok(index>=0);
    this.children.splice(index,0,node);moves++;
  }};
  let created=0,moves=0;
  const make=(id,isCard=true)=>({dataset:{projectId:id},classList:{contains:()=>isCard},
    get nextElementSibling(){return container.children[container.children.indexOf(this)+1]||null;},
    remove(){container.children.splice(container.children.indexOf(this),1);}});
  const context=vm.createContext({});vm.runInContext(cards,context);
  context.createProjectCard=p=>{created++;return make(p.id);};context.updateProjectCard=(node,p)=>node.data=p;
  container.children.push(make('empty',false));
  const render=ids=>context.reconcileProjectCards(container,ids.map(id=>({id,revision:created})));
  render(['a','b']);const [a,b]=container.children;
  render(['a','b']);assert.equal(created,2);assert.equal(moves,2);assert.equal(container.children[0],a);
  render(['b','c','a']);assert.deepEqual(container.children.map(n=>n.dataset.projectId),['b','c','a']);assert.equal(container.children[0],b);assert.equal(container.children[2],a);
  render(['a']);assert.deepEqual(container.children,[a]);assert.equal(created,3);
});

function refreshContext(){
  let finish,reads=0,draws=0;
  const state={navigation:1,channel:{id:'c'},projects:[]};
  const context=vm.createContext({state,api:()=>{reads++;return new Promise(resolve=>finish=resolve);},renderOverview:()=>draws++});
  vm.runInContext(app.slice(app.indexOf('const overviewProjectRequests='),app.indexOf('function renameProject(')),context);
  return {state,context,finish:data=>finish(data),reads:()=>reads,draws:()=>draws};
}
test('concurrent overview refreshes share one read and one render',async()=>{
  const f=refreshContext(),first=f.context.refreshProjects(),second=f.context.refreshProjects();
  assert.equal(f.reads(),1);f.finish({projects:[{id:'p'}]});await Promise.all([first,second]);
  assert.equal(f.draws(),1);assert.equal(f.state.projects[0].id,'p');
  const again=f.context.refreshProjects();assert.equal(f.reads(),2);f.finish({projects:[]});await again;assert.equal(f.draws(),2);
});
test('a response from before reopening the same channel cannot refresh its newer view',async()=>{
  const f=refreshContext(),pending=f.context.refreshProjects();
  f.state.navigation++;f.state.projects=[{id:'new'}];
  f.finish({projects:[{id:'old'}]});await pending;
  assert.equal(f.draws(),0);assert.equal(f.state.projects[0].id,'new');
});
