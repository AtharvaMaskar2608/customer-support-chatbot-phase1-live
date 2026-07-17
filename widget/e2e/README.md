# Agent-driven E2E

`drive.mjs` is the reproducible form of the agent-run acceptance check required
by the `widget-shell` proposal (done-condition item 7): it drives the built
widget on the mock dev server through a real Chromium and asserts the rendered
blocks along the P&L flow (entry surface → free-text message → stepper chips →
delivered file card).

It is intentionally **not** a widget dependency — the widget's default install
stays free of a browser download. Run it on demand.

## Run

```bash
# Terminal A — serve the widget against the mock (single network surface)
npm --prefix widget run dev:mock          # http://localhost:5178

# Terminal B — drive it
npm i -g playwright-core                   # once (or have it resolvable)
node widget/e2e/drive.mjs
```

Expected output: `SUMMARY: 6/6 passed`, console clean.

## Notes

- Chromium is discovered from `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, else the
  `ms-playwright` cache (`npx playwright install chromium` to populate it).
- `--no-sandbox` is passed because CI/container kernels frequently block
  unprivileged user namespaces (Chromium then fails with "No usable sandbox").
  That same restriction is why the gstack `/browse` daemon and the project
  Playwright MCP could not launch in the build environment; this script is the
  equivalent agent-driven pass using the same engine.
- Override the target with `WIDGET_URL=http://host:port node widget/e2e/drive.mjs`.
