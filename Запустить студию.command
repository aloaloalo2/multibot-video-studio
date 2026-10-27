#!/bin/zsh
set -e
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
studio_url='http://127.0.0.1:8770/'
if /usr/bin/curl -fsS --max-time 2 'http://127.0.0.1:8770/api/health' | /usr/bin/grep -q 'multibot-video-studio'; then
  /usr/bin/open "$studio_url"
  exit 0
fi
/usr/bin/python3 backend/updater.py --at-start
/usr/bin/python3 backend/app.py --host 127.0.0.1 --port 8770 &
studio_pid=$!
for attempt in {1..60}; do
  if /usr/bin/curl -fsS --max-time 1 'http://127.0.0.1:8770/api/health' | /usr/bin/grep -q 'multibot-video-studio'; then
    /usr/bin/open "$studio_url"
    wait "$studio_pid"
    exit $?
  fi
  /bin/sleep 0.25
done
echo 'Студія не запустилася. Перевірте повідомлення вище.'
kill "$studio_pid" 2>/dev/null || true
exit 1
