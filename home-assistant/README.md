# Home Wallboard control for Home Assistant

The custom integration exposes a wallboard as a device with switches, selectors, time fields, number fields and status sensors. Settings synchronize in both directions. The tablet initiates the connection to HA's existing WebSocket API; no tablet network listener, broker or port forwarding is needed. Tested with Home Assistant Core 2026.10.4.

## Installation

1. Copy `custom_components/home_wallboard` into HA's `/config/custom_components/` and restart Home Assistant.
2. Generate a random pairing key of at least 32 characters, for example `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Keep it private.
3. Add **Home Wallboard** under **Settings → Devices & services → Add integration**. Choose a device ID (lowercase letters, digits, underscores), the HA user whose token the tablet already uses, and the pairing key.
4. Add the same values as `ha_control_device_id` and `ha_control_secret` to the tablet's private `/etc/wallboard/config.json`. Restart its `wallboard` service. Its existing `ha_url` and `ha_token` are reused. Do not put the pairing key in preferences or source control.
5. Add entities from the new device to a native HA dashboard. There are 46 entities: screen on/off, current/startup view, appearance/language/time, visibility, night schedule, brightness, idle/slideshow timing, photo source/album, temperature/weather sources, timer sound/outputs/volume and device status.

Use **Configure** on the integration for the room-labelled lamp selector (maximum nine), city search, photo source/album selection, and protected account dialogs. Add a navigation button to `/config/integrations/integration/home_wallboard` on an administrator dashboard for these dialogs. Any administrator can configure accounts; do not give untrusted users HA administrator access.

## Accounts and photos

Account passwords and Google client JSON are sent in authenticated AES-GCM command envelopes and are not saved in HA entry options, entity states, attributes, diagnostics or dashboards. Only the pairing key and user/device identity are stored in HA's config entry. The tablet retains the existing private account/session storage. Commands are bound to the device and request, expire after 90 seconds and are rejected on replay. The subscription requires both the configured HA user and a fresh HMAC pairing proof.

An iCloud calendar requires Apple's app-specific password. Private iCloud Photos requires the normal Apple login and possibly the separate six-digit verification dialog. Login/import runs in the tablet's background worker; check its Accounts page for completion/errors. Do not repeatedly submit credentials while login is in progress. Changing the calendar also changes Family Planner's shared calendar connection.

Google's first OAuth login must run in a browser **on the tablet**, because the Desktop OAuth callback is loopback-only. After authorization, private Google Photos selections can be opened from HA's configuration dialog and imported after finishing the selection. Picker imports selected images; it is not unattended album synchronization. No public sharing is required.

## Availability and safety

The tablet reports every five seconds. Controls become unavailable on disconnect or after 25 seconds without a report. Settings remain stored locally and the wallboard continues working if the control integration is unavailable. Native HA services can also be used in automations. A fire alarm takes priority over remote screen-off and view commands; a finished timer keeps the screen awake. Wake commands temporarily override the night schedule in the same way as a touch.

The dashboard's time field presentation follows the HA user's locale. The wallboard's 12h/24h setting controls the tablet, its own time pickers and its embedded planner; times are stored canonically as HH:MM.

Run the root project's offline test suite and lint checks to validate the protocol and integration source. The two protocol files are intentionally identical and checked by a test.
