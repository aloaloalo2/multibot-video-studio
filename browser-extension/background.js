// VideoKey Studio in the browser's toolbar (user, 1 November 2026: «в розширенні нажати і команда спрацьовує на
// комп'ютері»). A click opens the studio, or brings its tab forward; when the studio is down, the helper on this Mac
// (host/videokey_host.py, set up by «Встановити.command») runs «Запустить студию.command», and the tab opens once the
// studio answers. The helper does nothing else, and only this extension may call it.
const STUDIO = 'http://127.0.0.1:8770/';
const HOST = 'com.videokey.studio';

async function alive() {
  try {
    const response = await fetch(STUDIO + 'api/health', {cache: 'no-store'});
    return response.ok && (await response.text()).includes('multibot-video-studio');
  } catch { return false; }
}

function badge(text, color) {
  chrome.action.setBadgeText({text});
  if (color) chrome.action.setBadgeBackgroundColor({color});
}

async function openStudio() {
  const [tab] = await chrome.tabs.query({url: STUDIO + '*'});
  if (tab) { await chrome.tabs.update(tab.id, {active: true}); await chrome.windows.update(tab.windowId, {focused: true}); }
  else await chrome.tabs.create({url: STUDIO});
}

chrome.action.onClicked.addListener(async () => {
  if (await alive()) { badge(''); return openStudio(); }
  badge('…', '#3b8bff');
  chrome.action.setTitle({title: 'Запускаю VideoKey Studio…'});
  chrome.runtime.sendNativeMessage(HOST, {command: 'start'}, async reply => {
    chrome.action.setTitle({title: 'Відкрити VideoKey Studio'});
    if (chrome.runtime.lastError || !reply?.ok) {
      badge('!', '#d64545');
      const reason = chrome.runtime.lastError
        ? 'Помічник не встановлений: двічі клацніть «Встановити.command» у теці browser-extension студії.'
        : (reply?.error || 'Студія не запустилася.');
      chrome.action.setTitle({title: reason});
      chrome.tabs.create({url: 'data:text/html;charset=utf-8,' + encodeURIComponent(`<meta charset="utf-8"><body style="font:16px system-ui;background:#111;color:#eee;padding:40px"><h2>VideoKey Studio не запустилася</h2><p>${reason}</p></body>`)});
      return;
    }
    badge('');
    openStudio();
  });
});
