# Публікація випуску на YouTube

Робочий порядок з першої вдалої публікації 19 листопада 2026 року (Космос PRO, «Может ли тайна черных дыр объяснить наше
существование?», заплановано на 24.11 о 15:00, https://youtu.be/HvwtqPOgy6o). Кнопка «Опублікувати на YouTube» на картці
випуску дає готове завдання для нової сесії Claude з посиланням на цей файл.

## Правила автора

- Тільки вбудований браузер додатку (`mcp__Claude_Browser__*`), не Chrome. Google-акаунт може бути будь-який, у який
  автор увійшов у браузері на цьому комп'ютері (на одному Mac це технічний акаунт): головне, щоб ролик пішов саме на
  канал цього випуску. Перед завантаженням перевір назву каналу в Studio. Пароль, коди й вибір акаунта робить сам автор.
- Вікна Finder не відкривати: файли кладуться у форму скриптом (крок 3).
- Розклад: один ролик на день. У Studio → Контент знайти дату останнього запланованого (або вже вийшлого, якщо
  запланованих нема) і планувати на наступний день, 13:00–18:00 (зазвичай 15:00). Доступ «Приватне» + дата.
- Назва: перший із трьох тайтлів. Опис і теги з «Метаданные.txt». Прев'ю: «Превью.png». Аудиторія: «не для дітей».
  Плейлист каналу, якщо він є. Поле про використання ШІ (змінений контент) не чіпати. A/B-тест назв: якщо Studio
  показує кнопку, додати інші тайтли; немає кнопки, пропустити.
- Звук браузера вимкнений, вкладку після роботи закрити.

## Кнопка «Опублікувати»

Кнопка на картці ставить випуск у чергу студії. Якщо на цьому Mac уже працює сесія публікації (у неї у фоні
`python3 "VideoKey Studio/tools/youtube_publish.py" wait`, Bash із run_in_background), вона прокидається, коли `wait`
закінчується й друкує id випуску, публікує його й одразу знову запускає `wait`. Чекання не витрачає токенів. Якщо такої
сесії немає (інший комп'ютер, перезапуск додатку), кнопка відкриває нову сесію Claude Code з готовим завданням
(`claude://code/new?prompt=…`); автор натискає Enter, сесія публікує цей випуск і далі сама стає сесією публікації.
У її вбудованому браузері має бути вхід у YouTube. `queue` показує чергу.

## Кроки

1. `python3 "VideoKey Studio/tools/youtube_publish.py" prepare <id проєкту>` друкує назви, опис, теги, ID каналу YouTube,
   плейлист і адреси файлів, і запускає локальний сервер файлів на 127.0.0.1:8899. Поле `published` не порожнє: випуск
   уже викладено, зупинись і скажи автору.
2. Канал. Якщо `youtube_channel_id` відомий: `https://studio.youtube.com/channel/<id>/videos/upload`. Якщо ні, знайди
   канал на `https://www.youtube.com/channel_switcher`, клікни його, ID візьми так:
   `(await fetch('/@'+encodeURIComponent('ХЕНДЛ')).then(r=>r.text())).match(/"channelId":"(UC[\w-]{22})"/)[1]`
   і запиши: `youtube_publish.py channel <id проєкту> UC…`. Подивись у «Контенті» дату останнього запланованого ролика.
3. Діалог завантаження відкривай кнопками Studio через JS (пряма адреса `?d=ud` інколи блокується):
   кнопка «Создать» (`ytcp-button#create-icon`), потім пункт `tp-yt-paper-item` «Добавить видео». Відео в поле:
   ```js
   window.__up={state:'start'};(async()=>{try{const r=await fetch('VIDEO_URL');const total=+r.headers.get('content-length');
   const rd=r.body.getReader();const parts=[];let got=0;while(true){const {done,value}=await rd.read();if(done)break;
   parts.push(value);got+=value.length;window.__up={state:'dl',got,total};}
   const f=new File(parts,'НАЗВА.mp4',{type:'video/mp4'});const dt=new DataTransfer();dt.items.add(f);
   const i=document.querySelector('input[type=file][name=Filedata]');i.files=dt.files;i.dispatchEvent(new Event('change',{bubbles:true}));
   window.__up={state:'set',size:f.size};}catch(e){window.__up={state:'err',msg:e.message}}})();
   ```
   Прогрес читай `JSON.stringify(window.__up)`.
4. Назва й опис: `el.focus(); document.execCommand('selectAll'); document.execCommand('insertText', false, текст)` для
   `#title-textarea #textbox` і `#description-textarea #textbox`.
5. Прев'ю: той самий спосіб, що й відео, з `COVER_URL` у `ytcp-thumbnail-uploader input[type=file]`.
6. Аудиторія: `tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]`. Кнопка «Развернуть» відкриває теги.
   Теги вводь справжнім набором (`computer type`) через кому з комою в кінці, потім blur: присвоєння значення скриптом
   лишає лічильник 0/500. Плейлист: відкрий список, постав галочку, «Готово».
7. `#next-button` тричі до «Доступ». Там `#privacy-radios [name=PRIVATE]`, розгорни «Запланировать», вибери дату в
   календарі, час вибери зі списку (пункт «15:00»), а не набирай. Кнопки внизу діалогу клікай через JS
   (`#next-button`, `#done-button`): вузька панель зсуває координати. Перевір дату й час перед `#done-button`.
8. Після «Видео запланировано»: `youtube_publish.py done <id проєкту> <VIDEO_ID> "РРРР-ММ-ДД ГГ:ХХ"` і
   `youtube_publish.py stop`. Скажи автору дату, час і посилання.
