#!/bin/bash
# Runs inside the dedicated kiosk user's graphical session.
# D-Bus activation must use the same fullscreen stacking behavior.
mkdir -p "$HOME/.local/share/dbus-1/services"
cat > "$HOME/.local/share/dbus-1/services/org.onboard.Onboard.service" <<'EOF'
[D-BUS Service]
Name=org.onboard.Onboard
Exec=/usr/bin/onboard --quirks=compiz
EOF
gsettings set org.onboard start-minimized true
gsettings set org.onboard show-status-icon false
gsettings set org.onboard show-tooltips false
gsettings set org.onboard layout 'Full Keyboard'
gsettings set org.onboard.auto-show enabled false
gsettings set org.onboard.window docking-enabled true
gsettings set org.onboard.window docking-edge 'bottom'
gsettings set org.onboard.window docking-shrink-workarea false
gsettings set org.onboard.window force-to-top true
gsettings set org.onboard.window window-decoration false
gsettings set org.onboard.window.landscape dock-expand true
gsettings set org.onboard.window.landscape dock-height 400
gsettings set org.onboard.window.portrait dock-expand true
gsettings set org.onboard.window.portrait dock-height 400
gsettings set org.onboard.typing-assistance.word-suggestions enabled false
gsettings set org.onboard.typing-assistance.word-suggestions stealth-mode true
