# Security

This application is designed for a trusted local kiosk. Keep the HTTP server bound to loopback. HA, Immich, Google and Apple credentials live on the device, outside the checkout. Backups can contain credentials and personal media and must remain private.

Report vulnerabilities privately to the repository owner using GitHub's private vulnerability reporting when enabled. Do not post account files, signed image URLs, logs with personal data or tokens in public issues.

Supported development line: 0.3.x. No security service-level guarantee is provided. Before updating, back up private configuration and review dependency changes, then run the offline tests and check the device's integrations.

The optional HA control integration authenticates the configured tablet user and pairing key, encrypts commands, and expires/rejects replayed requests. Keep pairing keys private and restrict account configuration/dashboard access to trusted HA administrators. Prefer TLS for HA where available; command encryption does not conceal ordinary HA state reports or replace transport security. Diagnostics omit entry data and account identity.
