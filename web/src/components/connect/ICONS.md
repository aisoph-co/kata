# Connect platform icons — sources & licences

Inline SVG only, fetched once and committed (`PlatformIcon.tsx`) — the page
loads no external asset at runtime.

| Platform | Source | Licence | Notes |
|---|---|---|---|
| Discord | [`simple-icons`](https://www.npmjs.com/package/simple-icons) npm package v16.30.0, `siDiscord` | MIT (path data) | Single path + official hex `#5865F2` |
| Telegram | `simple-icons` v16.30.0, `siTelegram` | MIT (path data) | Single path + official hex `#26A5E4` |
| WhatsApp | `simple-icons` v16.30.0, `siWhatsapp` | MIT (path data) | Single path + official hex `#25D366` |
| Slack | Wikimedia Commons, [`File:Slack icon 2019.svg`](https://commons.wikimedia.org/wiki/File:Slack_icon_2019.svg) | `{{PD-textlogo}}` + `{{Trademark}}` — public domain as a simple geometric mark (below the threshold of originality); the Slack name/mark itself remains a trademark of Salesforce/Slack Technologies | Not in current `simple-icons` — pulled pending the trademark owner's permission, [simple-icons/simple-icons#14140](https://github.com/simple-icons/simple-icons/issues/14140) |
| Teams | Wikimedia Commons, [`File:Microsoft Office Teams (2019–2025).svg`](https://commons.wikimedia.org/wiki/File:Microsoft_Office_Teams_(2019%E2%80%932025).svg) | `{{PD-textlogo}}` + `{{Trademark}}` — same basis as Slack; Teams/Microsoft marks remain Microsoft's trademarks | 2019–2025 official design used, not the current 2025–present multi-gradient redesign (also on Commons, [`File:Microsoft Office Teams (2025–present).svg`](https://commons.wikimedia.org/wiki/File:Microsoft_Office_Teams_(2025%E2%80%93present).svg)) — the newer mark is ~4.1 KB even minified (a dozen radial gradients) and reads worse at the 24–28px size this UI renders icons at; both are still Microsoft-published marks |

All five downloaded once (2026-09-10), minified with `svgo` (`--multipass`),
under 4.2 KB each. No network calls at runtime — see `Connect`'s own
"nothing here calls the API" copy and `demo-web/README.md`'s "Never
touches" table.
