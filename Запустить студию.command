#!/bin/zsh
set -e
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
studio_url='http://127.0.0.1:8770/'
# the browser extension's helper starts the studio with VIDEOKEY_NO_OPEN=1: the extension opens the tab itself
open_studio() { [[ -n "$VIDEOKEY_NO_OPEN" ]] || /usr/bin/open "$studio_url"; }
# Opened by a double click, this runs in a Terminal window: it closes once the studio is up (user, 1 November 2026:
# «термінал тоді увімкнений, а я так не хочу»). The studio runs in a session of its own, so Terminal has nothing to
# ask about; a failure keeps the window open with its message.
close_window() {
  [[ "$TERM_PROGRAM" == "Apple_Terminal" && -z "$VIDEOKEY_NO_OPEN" ]] || return 0
  # a studio an older version started from a Terminal window still hangs on that window's terminal: closing Terminal
  # would take it down, so the window stays (user, 1 November 2026: «термінал закривається і студія перестає»)
  local studio_pid="$(/usr/sbin/lsof -tiTCP:8770 -sTCP:LISTEN 2>/dev/null | /usr/bin/head -1)"
  [[ -n "$studio_pid" && "$(/bin/ps -o tty= -p "$studio_pid" | /usr/bin/tr -d ' ')" == "??" ]] || return 0
  local tty_name="$(/usr/bin/tty)"
  # the window closes, and Terminal quits too when no other window of it is open (no dot left under it in the Dock)
  ( /bin/sleep 0.3; /usr/bin/osascript -e "tell application \"Terminal\"" \
      -e "close (every window whose selected tab's tty is \"$tty_name\")" \
      -e "if (count of windows) is 0 then quit" -e "end tell" >/dev/null 2>&1 ) &!
}
if /usr/bin/curl -fsS --max-time 2 'http://127.0.0.1:8770/api/health' | /usr/bin/grep -q 'multibot-video-studio'; then
  open_studio
  close_window
  exit 0
fi
/usr/bin/python3 backend/updater.py --at-start
umask 077
# tools/studio_restart.start: the server in its own session (not tied to this window), waits until it answers
if /usr/bin/python3 -c 'import sys; sys.path.insert(0, "tools"); import studio_restart; studio_restart.start()'; then
  open_studio
  close_window
  exit 0
fi
echo "Студія не запустилася. Діагностика: $HOME/Library/Logs/VideoKey Studio/server.log"
exit 1
