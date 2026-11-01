#!/bin/zsh
set -e
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
studio_url='http://127.0.0.1:8770/'
# the browser extension's helper starts the studio with VIDEOKEY_NO_OPEN=1: the extension opens the tab itself
# the helper opens this through macOS (no environment passes), so it leaves a fresh marker instead
no_open_marker="$HOME/Library/Caches/VideoKey Studio/no-open"
if [[ -f "$no_open_marker" && $(( $(/bin/date +%s) - $(/usr/bin/stat -f %m "$no_open_marker") )) -lt 120 ]]; then
  VIDEOKEY_NO_OPEN=1
  VIDEOKEY_FROM_HELPER=1
fi
/bin/rm -f "$no_open_marker"
open_studio() { [[ -n "$VIDEOKEY_NO_OPEN" ]] || /usr/bin/open "$studio_url"; }
# Opened by a double click, this runs in a Terminal window. The window is hidden once the studio is up (not minimized
# into the Dock either, user: «в док не хочу»), never closed: on the author's Mac closing it, or quitting Terminal, took the studio down (1 November 2026, the
# server log ends with no error). A failure keeps the window in front with its message.
hide_window() {
  [[ "$TERM_PROGRAM" == "Apple_Terminal" && ( -z "$VIDEOKEY_NO_OPEN" || -n "$VIDEOKEY_FROM_HELPER" ) ]] || return 0
  local tty_name="$(/usr/bin/tty)"
  ( /bin/sleep 0.3; /usr/bin/osascript -e "tell application \"Terminal\" to set visible of (every window whose selected tab's tty is \"$tty_name\") to false" >/dev/null 2>&1 ) &!
}
if /usr/bin/curl -fsS --max-time 2 'http://127.0.0.1:8770/api/health' | /usr/bin/grep -q 'multibot-video-studio'; then
  open_studio
  hide_window
  exit 0
fi
/usr/bin/python3 backend/updater.py --at-start
umask 077
# tools/studio_restart.start: the server in its own session (not tied to this window), waits until it answers
if /usr/bin/python3 -c 'import sys; sys.path.insert(0, "tools"); import studio_restart; studio_restart.start()'; then
  open_studio
  hide_window
  exit 0
fi
echo "Студія не запустилася. Діагностика: $HOME/Library/Logs/VideoKey Studio/server.log"
exit 1
