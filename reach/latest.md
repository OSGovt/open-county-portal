# Reach measurements, 2026-10-17

GitHub traffic: see docs/traffic/traffic.csv (not readable with the Actions token)

Agent access:
  https://utopia.osgovt.com: home 503, robots error: ReadTimeout, sitemap 503, llms.txt error: ReadTimeout; blocked at home: unknown (robots.txt not readable)
  https://osgovt.com: home error: ConnectError, robots error: ConnectError, sitemap error: ConnectError, llms.txt error: ConnectError; blocked at home: unknown (robots.txt not readable)

Search Console: google-auth missing

Bing Webmaster: not connected

Not measured this week:
- GitHub traffic: skipped. The traffic API needs a token with push access, which the Actions token lacks; the nightly maintenance task records it (docs/traffic/traffic.csv, reach/github.csv).
- Search Console: skipped (google-auth not installed)
- Bing Webmaster: skipped (BING_WEBMASTER_API_KEY not set)
