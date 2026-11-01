// VideoKey Studio (пользователь, 2026-11-01: «пятая полоска… большая кнопка, переходит в студию, если закрыта, запускает»).
// Студия отвечает: открываем её вкладку или переходим на уже открытую, команду не трогаем. Не отвечает: помощник
// студии на Mac (com.videokey.studio, ставит «Встановити.command» в папке browser-helper студии) запускает
// «Запустить студию.command», и вкладка открывается, когда студия ответит.
const STUDIO_URL = "http://127.0.0.1:8770/";
const studioBtn = document.getElementById("studioOpen");
const studioLabel = document.getElementById("studioLabel");
const studioNote = document.getElementById("studioNote");

async function studioAlive() {
  try {
    const r = await fetch(STUDIO_URL + "api/health", { cache: "no-store" });
    return r.ok && (await r.text()).includes("multibot-video-studio");
  } catch (e) { return false; }
}

async function studioShow() {
  const [tab] = await chrome.tabs.query({ url: STUDIO_URL + "*" });
  if (tab) {
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url: STUDIO_URL });
  }
  window.close();
}

function studioFail(text) {
  studioBtn.disabled = false;
  studioLabel.textContent = "Открыть";
  studioNote.textContent = text;
  studioNote.hidden = false;
}

studioBtn.addEventListener("click", async () => {
  studioNote.hidden = true;
  if (await studioAlive()) return studioShow();
  studioBtn.disabled = true;
  studioLabel.textContent = "Запускаю…";
  try {
    chrome.runtime.sendNativeMessage("com.videokey.studio", { command: "start" }, (reply) => {
      if (chrome.runtime.lastError) {
        const why = chrome.runtime.lastError.message || "";
        return studioFail(/not found/i.test(why)
          ? "Студия закрыта, а помощник запуска не установлен. Дважды щёлкните «Встановити.command» в папке browser-helper студии."
          : "Помощник запуска не сработал: " + why + ". Запустите студию «Запустить студию.command» и пришлите эту строку.");
      }
      if (!reply || !reply.ok) return studioFail((reply && reply.error) || "Студия не запустилась.");
      studioShow();
    });
  } catch (e) {
    studioFail("Студия закрыта. Запустите «Запустить студию.command» в папке студии.");
  }
});

