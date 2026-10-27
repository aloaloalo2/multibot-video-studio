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
umask 077
studio_log_dir="$HOME/Library/Logs/MultiBot Video Studio"
/bin/mkdir -p "$studio_log_dir"
/usr/bin/nohup /usr/bin/python3 -u backend/app.py --host 127.0.0.1 --port 8770 >>"$studio_log_dir/server.log" 2>&1 </dev/null &
studio_pid=$!
for attempt in {1..60}; do
  if /usr/bin/curl -fsS --max-time 1 'http://127.0.0.1:8770/api/health' | /usr/bin/grep -q 'multibot-video-studio'; then
    /usr/bin/open "$studio_url"
    exit 0
  fi
  /bin/sleep 0.25
done
echo "Студія не запустилася. Діагностика: $studio_log_dir/server.log"
kill "$studio_pid" 2>/dev/null || true
exit 1
