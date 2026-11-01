#!/bin/zsh
# Sets up the helper of the «VideoKey Studio» browser extension: tells Chrome, Arc, Brave, Edge, Chromium and Yandex
# Browser that the extension may start the studio through host/videokey_host.py. Run once; again after moving the
# studio's folder.
set -e
cd "${0:A:h}"
host="$PWD/host/videokey_host.py"
chmod +x "$host"
manifest='{"name":"com.videokey.studio","description":"Starts VideoKey Studio","path":"'"$host"'","type":"stdio","allowed_origins":["chrome-extension://ekndpgojnpfpnljcbdkenoecglhjjpdk/"]}'
done_any=0
for app in "Google/Chrome" "Google/Chrome Beta" "Chromium" "Arc/User Data" "BraveSoftware/Brave-Browser" "Microsoft Edge" "Yandex/YandexBrowser"; do
  base="$HOME/Library/Application Support/$app"
  if [[ -d "$base" ]]; then
    /bin/mkdir -p "$base/NativeMessagingHosts"
    print -r -- "$manifest" > "$base/NativeMessagingHosts/com.videokey.studio.json"
    echo "Готово для: $app"
    done_any=1
  fi
done
if [[ $done_any == 0 ]]; then
  echo "Не знайдено браузера на основі Chrome (Chrome, Arc, Brave, Edge, Яндекс)."
  exit 1
fi
echo
echo "Тепер додайте саме розширення:"
echo "1. Відкрийте в браузері сторінку chrome://extensions"
echo "2. Увімкніть «Режим розробника» (Developer mode) угорі праворуч"
echo "3. Натисніть «Завантажити розпаковане» (Load unpacked) і виберіть теку: $PWD"
echo "4. Закріпіть значок VideoKey на панелі браузера (значок пазла → кнопка-шпилька)"
