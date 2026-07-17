# Jini Prototype — Shared Design Brief

> **Read this first.** All three prototype deliverables (overview, interactive
> prototype, per-flow screens) MUST use these exact tokens and component styles
> so they look like one product in proposals. Content/behavior source of truth:
> `../technical/02_technical_spec.md`, `../technical/03_finx_api_reference.md`,
> `../technical/04_freshdesk_api_reference.md`, `../customer_support_chatbot_phase1.md`.
> Existing visual references: `../Jini Widget Screens.html`,
> `../contract-note-flow-screens (1).html`.

## Product in one line
**Choice Jini** — a WhatsApp-style, post-login support chatbot embedded in the
FinX trading app. It (a) fulfils report requests as downloadable file cards and
(b) answers factual questions from a knowledge base (RAG). Always reachable:
raise a Freshdesk ticket + a call-support chip.

## Design tokens (FinX theme)
```css
:root{
  --brand:#2B6BE8; --brand-ink:#1B4FB0;
  --positive:#17B26A; --danger:#E5484D; --warn:#F5A524;
  --text:#1A1D21; --text-muted:#5F6B7A;
  --bg:#FFFFFF; --surface:#F7F9FC; --border:#D5DCE6;
  --bubble-bot:#F1F5FB; --bubble-user:#2B6BE8; --bubble-user-ink:#FFFFFF;
  --radius:14px; --radius-sm:10px; --radius-chip:999px;
  --shadow:0 6px 24px rgba(20,29,45,.12);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,Menlo,monospace;
}
```
- Support light + dark (`@media (prefers-color-scheme:dark)`): dark `--bg:#0F1620`,
  `--surface:#182231`, `--text:#E7ECF3`, `--border:#26period`… keep brand blue.
- Font = system stack only (mockups name no brand face). Never load web fonts.
- Self-contained HTML: inline all CSS/JS, embed any icon as inline SVG/emoji.
  No external requests (works offline, drops straight into a proposal).

## The widget frame
- Floating chat, **~400×640**, bottom-right, `--shadow`, `--radius`. Header:
  avatar ✦ "Choice Jini", "● online · X008593", "↺ Start over".
- Message list (scroll), then a chip row / input composer with placeholder
  "Ask anything about FinX…".
- Persistent footer disclaimer: **"Factual answers only — never investment
  advice."** and the trust line "Files land right here — no email verification."

## Component catalog (build these as reusable styles)
1. **Bot bubble** (`--bubble-bot`, left) / **User bubble** (`--bubble-user`,
   right, white text).
2. **Quick-reply chips** — pill (`--radius-chip`), `--surface` bg, `--border`,
   tap target ≥36px. Row wraps.
3. **Stepper card** — titled card with numbered steps (Segment → Date → Delivery);
   completed steps show the chosen value + are tappable to edit; active step
   shows chips.
4. **In-chat calendar** — month grid; out-of-range dates hard-disabled (greyed,
   not clickable). Per-flow bounds differ (see spec §2.5).
5. **File card** — icon + name + "182 KB · PDF · password: PAN" + a "Trouble
   opening it? Tell me." helper link. (CML/contract-note PDFs have **no**
   password.)
6. **Note-list card** (contract notes) — paginated 10/page, month dividers,
   per-row Download, segment badge (NSE·BSE vs MCX) only when a day has two
   notes.
7. **Data card** (brokerage / holdings) — rows rendered dynamically from the
   API (never hardcode segments/rows).
8. **Error bubble** — conversational, `--warn`/`--danger` accent, with recovery
   chips (↺ Retry · 🎫 Raise a ticket). NEVER a toast.
9. **Ticket confirmation** — "Ticket #48211 raised… within 24 hours. Track it
   anytime — ask 'ticket status'." + call-support chip.

## Chosen variants (locked)
- Entry surface: **1a** (Support section: time-aware greeting + "Popular right
  now" chips + free text). Second surface: 1b Reports screen (intent-first chips).
- P&L flow: **2a** (stepper card).

## Flows to cover (the 11 + RAG + ticket)
P&L · Ledger · MTF Ledger · Contract Notes · Tax Report / Capital Gain · CML ·
Brokerage · Holding · (Detailed/Global P&L) · RAG Q&A · Raise-ticket / call
support. Report delivery is always a **file card** (download or email to masked
registered address `san***.harsha@gmail.com`).

## Content & compliance rules (must appear where relevant)
- Post-login; greets by Client ID (`X008593`) in Phase 1.
- Email delivery only to the masked registered address; not editable in-bot.
- Never expose URLs / file_ids / raw API errors to the user.
- Caps: 10 messages/conversation; ≤2 follow-up questions per ambiguity → then
  offer ticket / call.
- Compliance footer always visible; RAG answers cite the KB and refuse
  investment advice.

## Language & tone
Warm, concise, ≤3 short paragraphs, WhatsApp-readable. English/Hindi/Hinglish
with sticky-language (English once → English thereafter).
