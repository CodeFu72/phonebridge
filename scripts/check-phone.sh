#!/bin/bash
set -u
project_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir" || exit 1
printf 'PhoneBridge — iPhone Bluetooth capability check\n\n'
printf 'Pair your iPhone using the Bluetooth settings on both devices first.\nOn the iPhone, open Settings > Bluetooth > (i) beside this laptop.\nEnable Show Notifications / Show Message Notifications if available.\n\n'
if ! pacman -Q bluez-obex >/dev/null 2>&1; then
  printf 'The messaging transport package bluez-obex is needed.\nInstalling it through Omarchy; your terminal may request your password.\n\n'
  if ! omarchy pkg add bluez-obex; then
    printf '\nPackage installation did not complete. No phone probe was run.\n'
    read -r -p 'Press Enter to close. ' _
    exit 1
  fi
fi
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/phonebridge"
mkdir -p "$state_dir"
chmod 700 "$state_dir"
report_dir=$(mktemp -d "$state_dir/run-XXXXXXXX")
report_path="$report_dir/capabilities.json"
python phonebridge.py --probe --report "$report_path"
result=$?
printf '\nThis was a capability check, not a successful message exchange.\n'
printf 'The saved report excludes message bodies, contact names and Bluetooth addresses.\n'
read -r -p 'Press Enter to close. ' _
exit "$result"
