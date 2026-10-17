# Reach measurements, 2026-10-17

GitHub traffic: see docs/traffic/traffic.csv (not readable with the Actions token)

Agent access:
  https://utopia.osgovt.com: home 200, robots 200, sitemap 200, llms.txt 200; blocked at home: ClaudeBot, GPTBot
  https://osgovt.com: home error: ConnectError, robots error: ConnectError, sitemap error: ConnectError, llms.txt error: ConnectError; blocked at home: unknown (robots.txt not readable)

Search Console: not connected

Bing Webmaster: not connected

Not measured this week:
- GitHub traffic: skipped. The traffic API needs a token with push access, which the Actions token lacks; the nightly maintenance task records it (docs/traffic/traffic.csv, reach/github.csv).
- Search Console: skipped (GSC_SERVICE_ACCOUNT_JSON not set)
- Bing Webmaster: skipped (BING_WEBMASTER_API_KEY not set)
