# Contributing

Use English for issues, pull requests, documentation and screenshots. Swedish translations are supported in the application; preserve both language options when changing the UI.

Run the tests, Python checks and frontend formatting checks listed in the README before opening a pull request. Explain the user-visible change and how it was verified. Keep device-specific configuration outside the repository.

For screenshots, start `examples/demo.py` and use `scripts/capture_screenshots.py`. This helper requires the synthetic-demo marker and refuses to capture the production wallboard. Use the English interface. Do not photograph or capture a real household dashboard, camera stream, calendar, account page, album or music history for an issue or pull request. Illustrations in the demo are original SVGs defined in the demo source.

Never commit tokens, passwords, pairing keys, cookies, OAuth client files, signed URLs, private photos or runtime backups. Submit security reports privately as described in SECURITY.md.
