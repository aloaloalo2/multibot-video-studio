// One absolute time axis for the original and the published translated phrases.
const langAlignmentState=new Map();
const langAlignmentLoads=new WeakMap();
function langAlignmentLoad(id,item,snapshot=langData){
  let loads=langAlignmentLoads.get(snapshot);
  if(!loads){loads=new Map();langAlignmentLoads.set(snapshot,loads);}
  const key=`${id}:${item.code}`;
  if(!loads.has(key))loads.set(key,api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/alignment`).catch(error=>{loads.delete(key);throw error;}));
  return loads.get(key);
}

function langAlignmentTempo(line,row){
  const speed=row===0?1:line?.speed;
  if(typeof speed!=='number'||!Number.isFinite(speed)||speed<=0)return {label:'?',description:'Швидкість цього запису не збережена'};
  const percent=Math.round((speed-1)*1000)/10;
  const amount=Math.abs(percent).toLocaleString('uk-UA',{maximumFractionDigits:1});
  return {label:`${amount}%`,icon:percent>0?'fast':percent<0?'slow':null,
    description:percent===0?'Без зміни швидкості':`${percent>0?'Прискорено':'Уповільнено'} на ${amount}%`};
}

function langAlignmentTempoIcon(tempo){
  if(!tempo.icon)return '';
  const shape=tempo.icon==='slow'
    ?'<path d="M4 15a7 7 0 0 1 14 0H4ZM7 15v3m8-3v3M4 14l-2-1m16 2h2a2 2 0 1 0-2-2"/>'
    :'<circle cx="17" cy="3.5" r="1.7" fill="currentColor" stroke="none"/><path d="m9 8 3-2 4 3 3 2 3-4M15 8l-4 6 5 3-1 5M11 14l-4 6H3M3 10h3M1 14h3"/>';
  return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${shape}</svg>`;
}

function langAlignmentCharacters(line,comparison,row){
  const raw=Array.from(line.text||'').length,normalized=comparison?.available===true;
  const count=normalized?comparison[row===0?'source_chars':'translated_chars']:raw;
  const difference=normalized?comparison.difference_percent:null;
  const change=row>0&&difference!==null?` (${difference>0?'+':difference<0?'−':''}${Math.abs(difference).toLocaleString('uk-UA',{maximumFractionDigits:1})}%)`:'';
  return {label:`${count.toLocaleString('uk-UA')} символів${change}`,
    title:normalized?`З урахуванням чисел: цифри та розпізнані числівники рахуються в однаковій цифровій формі. У тексті: ${raw.toLocaleString('uk-UA')} символів. Текст озвучки не змінено.`:'Символи з пробілами та пунктуацією. Порівняння з урахуванням чисел недоступне.'};
}

function langAlignmentPlayingPhrase(lines,audio){
  if(!audio||audio.paused||audio.ended)return null;
  const time=audio.currentTime;
  const line=lines.find(line=>time>=line.start&&time<line.end);
  return line?{index:line.index,progress:(time-line.start)/(line.end-line.start)}:null;
}

function langAlignment(id,item){
  const root=document.createElement('section');root.className='lang-alignment';
  root.setAttribute('aria-label','Порівняння озвучки');
  root.innerHTML='<div class="lang-alignment-head"><h2>Синхронізація фраз</h2><span class="lang-alignment-status" role="status">Завантаження…</span></div>';
  let observer=null,disposed=false,playbackFrame=null;
  const events=new AbortController();
  root.dispose=()=>{disposed=true;observer?.disconnect();events.abort();cancelAnimationFrame(playbackFrame);root.querySelectorAll('audio').forEach(audio=>audio.pause());};
  const load=async()=>{
    try{
      const data=await langAlignmentLoad(id,item);
      if(disposed||!root.isConnected||state.project?.id!==id)return;
      if(!data){throw new Error('Не вдалося завантажити таймінги. Відкрийте озвучку ще раз.');}
      if(!data.original.length||!(data.duration>0)){
        root.querySelector('.lang-alignment-status').textContent='Таймінги оригіналу ще не додані.';return;
      }
      const key=`${id}:${item.code}`,saved=langAlignmentState.get(key)||{};
      const rows=[data.original,data.translated||[]],names=[langOriginalName(),`${langFlag(item.code)} ${esc(item.name)}`];
      const rowData=[null,data];
      const messages={missing:'Озвучка цією мовою ще не готова.',outdated:'Після зміни тексту потрібно оновити озвучку.',timing_missing:'Для цього запису немає збережених таймінгів фраз.'};
      let zoom=saved.zoom||null,selected=Number.isInteger(saved.selected)?saved.selected:0,highlighted=saved.highlighted!==false,scale=1,active=null,playingIndex=null,stopAt=null;
      const compareRow=1;
      const playSvg='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 11 7-11 7z" fill="currentColor" stroke="none"/></svg>';
      const pauseSvg='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14" stroke="currentColor" stroke-width="4"/></svg>';
      const fmt=value=>`${clock(Math.max(0,value))}.${Math.floor((Math.max(0,value)%1)*10)}`;
      const seconds=value=>`${value.toFixed(1).replace('.',',')} с`;
      const scoreMarkup=value=>{
        const score=value?.synchronization;if(!score)return '';
        const title=`Оцінка збігу часу: середнє 100 × (1 − |зсув| / ${score.limit_seconds})² для кожної фрази, мінімум 0. Беремо більший зсув початку або кінця. Найбільший зсув: ${seconds(score.max_shift_seconds)}. Понад ±${score.limit_seconds} с: ${score.outside_limit} із ${score.phrases}.`;
        return `<span class="lang-alignment-score${score.outside_limit?' needs-review':''}" title="${esc(title)}">${score.percent.toLocaleString('uk-UA',{maximumFractionDigits:1})}% синхронності</span>`;
      };
      root.innerHTML=`<div class="lang-alignment-head"><h2>Синхронізація фраз</h2><span>${data.original.length} фраз</span>
        <div class="lang-alignment-zoom"><button type="button" data-zoom="out" aria-label="Зменшити масштаб порівняння">−</button><button type="button" data-zoom="fit" title="Показати весь ролик" aria-label="Показати весь ролик у порівнянні">100%</button><button type="button" data-zoom="in" aria-label="Збільшити масштаб порівняння">+</button></div></div>
        <div class="lang-alignment-grid"><div class="lang-alignment-labels"><div></div><div class="lang-alignment-row-label"><b>${names[0]}</b></div><div class="lang-alignment-row-label"><b>${names[1]}</b>${scoreMarkup(data)}${item.saved_mix?.state==='saved'&&data.status==='ready'?'<small class="lang-alignment-saved">✓ Файл збережено</small>':''}</div></div>
          <div class="lang-alignment-scroll" tabindex="0" aria-label="Спільна шкала часу"><div class="lang-alignment-canvas">
            <div class="lang-alignment-ruler"></div>${rows.map((_,row)=>`<div class="lang-alignment-track${row?' translated':''}" data-row="${row}" aria-label="Фрази: ${row?esc(item.name):'оригінал'}"></div>`).join('')}<i class="lang-alignment-playhead" aria-hidden="true" hidden></i>
          </div></div></div>
        <div class="lang-alignment-selection"><b></b><span></span></div><div class="lang-alignment-details"></div>
        <p class="lang-alignment-note" role="status"></p>`;
      const scroll=root.querySelector('.lang-alignment-scroll'),canvas=root.querySelector('.lang-alignment-canvas');
      const ruler=root.querySelector('.lang-alignment-ruler'),head=root.querySelector('.lang-alignment-playhead');
      const tracks=[...root.querySelectorAll('.lang-alignment-track')],details=root.querySelector('.lang-alignment-details');
      const note=root.querySelector('.lang-alignment-note'),selection=root.querySelector('.lang-alignment-selection');
      const available=[data.original_audio,data.translated_audio];
      const audios=available.map((enabled,row)=>{
        const audio=document.createElement('audio');audio.preload='none';
        if(enabled)audio.src=row===0?`/api/projects/${encodeURIComponent(id)}/languages/original`:langUrl(id,item.code,'voice',item.voice?.made_at);
        root.append(audio);return audio;
      });
      // Full-track players and phrase excerpts use the same row and absolute clock.
      const players=new Map(audios.map((audio,row)=>[audio,row]));
      const registerPlayer=audio=>{
        if(players.has(audio)||audio?.dataset?.alignmentProject!==id)return;
        if(audio.dataset.alignmentCode===item.code&&available[1])players.set(audio,1);
      };
      document.querySelectorAll('audio[data-alignment-project]').forEach(registerPlayer);
      function remember(){langAlignmentState.set(key,{zoom,selected,highlighted,scroll:scroll.scrollLeft});}
      function keepVisible(start,end){
        const left=start*scale,right=end*scale;
        if(left<scroll.scrollLeft+8)scroll.scrollLeft=Math.max(0,left-24);
        else if(right>scroll.scrollLeft+scroll.clientWidth-8)scroll.scrollLeft=Math.max(0,left-scroll.clientWidth*.3);
      }
      function paintPlayhead(follow=false){
        const row=players.get(active);
        const position=row==null?null:langAlignmentPlayingPhrase(rows[row],active);
        const phrase=position?tracks[row].querySelector(`[data-index="${position.index}"]`):null;
        head.hidden=!phrase;
        if(phrase){
          if(head.parentElement!==phrase)phrase.append(head);
          head.style.left=`${position.progress*100}%`;
        }
        if(row==null||active.paused||active.ended)return;
        const time=Math.max(0,Math.min(data.duration,active.currentTime));
        if(follow)keepVisible(time,time);
      }
      function tick(){
        playbackFrame=null;
        if(disposed||!root.isConnected||!active)return;
        if(stopAt!=null&&active.currentTime>=stopAt){
          const end=stopAt;stopAt=null;active.pause();active.currentTime=end;
        }
        paintPlayhead(!active.paused);
        if(!active.paused&&!active.ended)playbackFrame=requestAnimationFrame(tick);
      }
      function onPlay(event){
        const audio=event.target;
        if(!(audio instanceof HTMLMediaElement))return;
        registerPlayer(audio);
        cancelAnimationFrame(playbackFrame);playbackFrame=null;
        for(const other of players.keys())if(other!==audio)other.pause();
        if(active!==audio){playingIndex=null;stopAt=null;}
        active=players.has(audio)?audio:null;
        paintPlayhead(true);playbackButtons();
        if(active)playbackFrame=requestAnimationFrame(tick);
      }
      document.addEventListener('play',onPlay,{capture:true,signal:events.signal});
      function playbackButtons(){
        details.querySelectorAll('button[data-play-row]').forEach(button=>{
          const audio=audios[Number(button.dataset.playRow)],playing=active===audio&&playingIndex===selected&&!audio.paused;
          button.innerHTML=playing?pauseSvg:playSvg;button.setAttribute('aria-label',playing?'Призупинити фразу':`Прослухати фразу ${selected+1}`);
          button.setAttribute('aria-pressed',String(playing));
        });
      }
      function select(index,move=false,highlight=true){
        if(index===null){
          highlighted=false;
          root.querySelectorAll('.lang-alignment-phrase').forEach(button=>{
            button.classList.remove('selected','paired');button.setAttribute('aria-pressed','false');
          });
          remember();return;
        }
        selected=Math.max(0,Math.min(rows[0].length-1,index));
        highlighted=highlight;
        root.querySelectorAll('.lang-alignment-phrase').forEach(button=>{
          const match=Number(button.dataset.index)===selected;button.classList.toggle('selected',match&&highlighted);
          button.setAttribute('aria-pressed',String(match&&highlighted));button.tabIndex=match?0:-1;
        });
        const original=rows[0][selected],translated=rows[compareRow].find(line=>line.index===selected);
        const comparison=rowData[compareRow]?.character_comparisons?.find(entry=>entry.index===selected);
        selection.querySelector('b').textContent=`Фраза ${selected+1}`;
        const shift=translated?translated.start-original.start:null,endShift=translated?translated.end-original.end:null;
        const drift=value=>Math.abs(value)<.1?'збігається':`${Math.abs(value).toFixed(1).replace('.',',')} с ${value>0?'пізніше':'раніше'}`;
        const outside=shift!=null&&Math.max(Math.abs(shift),Math.abs(endShift))>data.limit_seconds;
        selection.querySelector('span').textContent=shift==null?'':`${outside?`Понад ±${data.limit_seconds} с · `:''}Початок ${drift(shift)} · кінець ${drift(endShift)}`;
        selection.classList.toggle('outside-limit',outside);
        details.innerHTML=[0,compareRow].map(row=>{
          const line=row===0?original:translated;
          const chars=line?langAlignmentCharacters(line,comparison,row):null;
          return `<div class="lang-alignment-detail"><div><b>${names[row]}</b>${chars?`<small class="lang-alignment-chars" title="${esc(chars.title)}">${chars.label}</small>`:''}<small>${line?`${fmt(line.start)} → ${fmt(line.end)}`:''}</small><button type="button" data-play-row="${row}"${line&&available[row]?'':' disabled'} aria-label="Прослухати фразу ${selected+1}">${playSvg}</button></div>${line?`<div class="lang-alignment-detail-meta"><span>Тривалість ${seconds(line.end-line.start)}</span><span title="${row===0?'Оригінальний запис':'Локальна зміна швидкості згенерованого запису'}">${langAlignmentTempo(line,row).description}</span></div>`:''}<p>${line?esc(line.text):esc(messages[rowData[row]?.status]||'Озвучка ще не готова.')}</p></div>`;
        }).join('');
        if(move)keepVisible(Math.min(original.start,translated?.start??original.start),Math.max(original.end,translated?.end??original.end));
        remember();playbackButtons();
      }
      function draw(){
        const width=Math.max(240,scroll.clientWidth);
        if(zoom==null)zoom=Math.max(1,Math.min(128,data.duration*6/width));
        scale=width/data.duration*zoom;canvas.style.width=`${width*zoom}px`;
        const step=[1,2,5,10,15,30,60,120,300,600].find(value=>value*scale>=80)||600;
        const marks=[];for(let time=0;time<data.duration;time+=step)marks.push(`<span style="left:${time*scale}px">${clock(time)}</span>`);
        ruler.innerHTML=marks.join('');
        tracks.forEach((track,row)=>{track.innerHTML=rows[row].map(line=>{
          const width=(line.end-line.start)*scale;
          const source=rows[0].find(entry=>entry.index===line.index);
          const shift=row>0&&source?Math.max(Math.abs(line.start-source.start),Math.abs(line.end-source.end)):0;
          const tempo=langAlignmentTempo(line,row),outside=Math.abs(shift)>data.limit_seconds;
          const tip=`Фраза ${line.index+1} · ${fmt(line.start)} → ${fmt(line.end)}\nТривалість ${seconds(line.end-line.start)} · ${tempo.description}${outside?`\nЗміщення понад ±${data.limit_seconds} с`:''}\n${line.text}`;
          return `<button type="button" class="lang-alignment-phrase${width<20?' narrow':''}${width<44?' compact':''}${outside?' outside-limit':''}" data-index="${line.index}" style="left:${line.start*scale}px;width:${Math.max(.5,width)}px" title="${esc(tip)}" aria-label="Фраза ${line.index+1}, ${fmt(line.start)} до ${fmt(line.end)}, ${esc(tempo.description)}${outside?', перевищено допустиме зміщення':''}"><span>${line.index+1}</span>${row>0?`<small class="lang-alignment-tempo">${langAlignmentTempoIcon(tempo)}${tempo.label}</small>`:''}</button>`;
        }).join('');
          if(row>0&&!rows[row].length){
            track.innerHTML=`<div class="lang-alignment-empty" style="width:${width}px">${data.status==='timing_missing'?'<span>Таймінги цього запису відсутні</span>':`<button type="button" class="secondary lang-alignment-generate" data-code="${item.code}">Згенерувати озвучку</button>`}</div>`;
          }
        });
        root.querySelector('[data-zoom="fit"]').textContent=`${Math.round(zoom*100)}%`;
        root.querySelector('[data-zoom="out"]').disabled=zoom<=1;root.querySelector('[data-zoom="in"]').disabled=zoom>=128;
        select(selected,false,highlighted);paintPlayhead();langPaintVoiceTiles();
      }
      root.querySelectorAll('[data-zoom]').forEach(button=>button.addEventListener('click',()=>{
        const middle=(scroll.scrollLeft+scroll.clientWidth/2)/scale;
        zoom=button.dataset.zoom==='fit'?1:Math.max(1,Math.min(128,zoom*(button.dataset.zoom==='in'?1.5:1/1.5)));
        draw();scroll.scrollLeft=Math.max(0,middle*scale-scroll.clientWidth/2);remember();
      }));
      canvas.addEventListener('click',event=>{
        const generate=event.target.closest('.lang-alignment-generate');
        if(generate){
          const entry=langData?.items.find(value=>value.code===generate.dataset.code);if(!entry)return;
          langConfirmVoice(id,entry.code);
          return;
        }
        const button=event.target.closest('.lang-alignment-phrase');if(button)select(Number(button.dataset.index));
      });
      root.addEventListener('click',event=>{
        if(!event.target.closest('button,a,input,select,textarea,.lang-alignment-details'))select(null);
      });
      document.addEventListener('pointerdown',event=>{
        if(!root.contains(event.target))select(null);
      },{signal:events.signal});
      canvas.addEventListener('keydown',event=>{
        const button=event.target.closest('.lang-alignment-phrase');if(!button||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        event.preventDefault();select(event.key==='Home'?0:event.key==='End'?rows[0].length-1:(selected??Number(button.dataset.index))+(event.key==='ArrowRight'?1:-1),true);
        button.parentElement.querySelector(`[data-index="${selected}"]`)?.focus({preventScroll:true});
      });
      const hover=index=>root.querySelectorAll('.lang-alignment-phrase').forEach(button=>button.classList.toggle('paired',Number(button.dataset.index)===index));
      canvas.addEventListener('pointerover',event=>{const button=event.target.closest('.lang-alignment-phrase');if(button)hover(Number(button.dataset.index));});
      canvas.addEventListener('pointerleave',()=>hover(-1));
      details.addEventListener('click',async event=>{
        const button=event.target.closest('[data-play-row]');if(!button)return;
        const row=Number(button.dataset.playRow),line=rows[row].find(value=>value.index===selected),audio=audios[row];
        if(!line||!available[row])return;
        if(active===audio&&playingIndex===selected&&!audio.paused){audio.pause();return;}
        document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause();});
        if(typeof stopPlayback==='function')stopPlayback();
        active=audio;playingIndex=selected;stopAt=line.end;
        try{audio.currentTime=line.start;paintPlayhead(true);await audio.play();}catch(error){note.textContent=`Не вдалося відтворити фразу: ${error.message}`;}
        playbackButtons();
      });
      document.addEventListener('timeupdate',event=>{
          const audio=event.target;
          if(active!==audio)return;
          if(stopAt!=null&&audio.currentTime>=stopAt){audio.pause();stopAt=null;}
          paintPlayhead(!audio.paused);
        },{capture:true,signal:events.signal});
        for(const name of ['pause','ended','seeking','seeked'])document.addEventListener(name,event=>{
          const audio=event.target;
          if(active===audio){
            if(audio.paused){cancelAnimationFrame(playbackFrame);playbackFrame=null;}
            paintPlayhead(name==='seeking'||name==='seeked');
          }
          playbackButtons();
        },{capture:true,signal:events.signal});
      scroll.addEventListener('scroll',remember,{passive:true});
      draw();scroll.scrollLeft=saved.scroll||0;
      const alreadyPlaying=[...players.keys()].find(audio=>!audio.paused&&!audio.ended);
      if(alreadyPlaying)onPlay({target:alreadyPlaying});
      observer=new ResizeObserver(()=>{if(root.isConnected)draw();});observer.observe(scroll);
    }catch(error){if(!disposed&&root.isConnected){const note=root.querySelector('.lang-alignment-status,.lang-alignment-note');if(note)note.textContent=error.message;}}
  };
  load();return root;
}
