#!/bin/bash
# Run from the clean release root. Never pass credentials on the command line.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo 'Run with sudo.' >&2; exit 1; fi
config_path="$(realpath "${1:?Usage: sudo bash deploy/install.sh /path/to/private-config.json}")"
python3 - "$config_path" <<'PY'
import json, sys
from urllib.parse import urlparse
c = json.load(open(sys.argv[1]))
for key in ('ha_url', 'ha_token', 'immich_url', 'immich_api_key', 'album_id'):
    assert isinstance(c.get(key), str) and c[key] and 'REPLACE' not in c[key], 'Configure ' + key
for key in ('ha_url', 'immich_url'):
    assert urlparse(c[key]).scheme in ('http', 'https'), 'Invalid service URL'
PY
apt-get update
apt-get install -y python3-venv python3-gi python3-opencv python3-numpy python3-gst-1.0 gstreamer1.0-libcamera libopencv-data chromium openbox unclutter onboard xdotool lightdm
id wallboard >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups video,render,audio wallboard
backup_dir="/var/backups/wallboard/$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup_dir"
if [ -f /etc/wallboard/config.json ]; then cp -a /etc/wallboard/config.json "$backup_dir/config.json"; fi
if [ -d /opt/wallboard ]; then cp -a /opt/wallboard "$backup_dir/app"; fi
install -d -m 0755 /opt/wallboard
cp app/*.py /opt/wallboard/
cp -r app/static /opt/wallboard/
python3 -m venv --system-site-packages /opt/wallboard/venv
/opt/wallboard/venv/bin/pip install -r requirements-runtime.txt
install -d -m 0750 -g wallboard /etc/wallboard
install -m 0640 -o root -g wallboard "$config_path" /etc/wallboard/config.json
install -d -m 0700 -o wallboard -g wallboard /var/lib/wallboard
install -m 0755 deploy/kiosk-session.sh deploy/configure-keyboard.sh /opt/wallboard/
install -m 0644 deploy/wallboard.service deploy/wallboard-presence.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wallboard.service
printf 'Open http://127.0.0.1:8090/ on the device. Configure kiosk/autologin and camera hardware separately.\n'
