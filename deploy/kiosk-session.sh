#!/bin/bash
export XDG_SESSION_TYPE=x11
xset s off
xset s noblank
xset -dpms
xsetroot -solid '#101817'
unclutter -idle 3 -root &
openbox &
/opt/wallboard/configure-keyboard.sh
/usr/bin/onboard --quirks=compiz &
mkdir -p "$HOME/.config/chromium-wallboard/Default"
while true; do
 /usr/bin/chromium --kiosk --no-first-run --no-default-browser-check --disable-session-crashed-bubble --disable-infobars --disable-features=Translate --password-store=basic --force-device-scale-factor=1.5 --user-data-dir="$HOME/.config/chromium-wallboard" http://127.0.0.1:8090/
 sleep 3
done
