Customer Support Chatbot
Technical Spec Document
Phase 1 - Liveyes 
System Overview 
This technical document covers the implementation of the agentic customer support chatbot phase 1 live details. In this phase we’ll be building a web page using react that can be integrated with mobile app, IOS and website as a web page. The goal of this project is to offload tasks from the customer support team. 

Architecture and Flow. 
The flow is going to look something like. 
The user opens the FinX app and enters the chat interface. 
The app shares the tokens, auth token etc from the frontend in the following way. 
https://finx.choiceindia.com/next/market/upcoming-ipo-list
?userId=oJPvImfcXeH781L51razRg%3D%3D
&sessionId=8NbSl45KYe9q5xS5ESuCIy2SRcxK%2F64VcXoQO93pqkQ%3D
&accessToken=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoX3RpbWUiOjE3ODM5MzYwNDcsImNsaWVudF9pZCI6IkZJTlgiLCJleHAiOjE3ODM5NjQ4NDcsImlkcCI6ImxvY2FsIiwiaXNzIjoiaHR0cHM6Ly9zc28uY2hvaWNlaW5kaWEuY29tIiwibW9iaWxlX251bWJlciI6Ik4yRTRORFkzTURaa1ltWTVNRGxoWVJvRXpCN3lRTU9yb1F5bnEyT3RDc1U9IiwibmJmIjoxNzgzOTM2MDQ3LCJzdWIiOiIwZDkzOTE4Zi1hYjM2LTQ5ZDktYjcwMS1mZTFkMTU2MjFlYTMifQ.ikcoOOShAPxEpCFxed7J3p91yn1dxerunxyhTnQfZshvRkInVnrbIpUslz9fE-cnpEQ7rghpai2s5VfOH2JXDufP0IEL47RgUh4OPSG-EPnDWZmxtvy-11xRDZW5VFLo5CJj4cVsgumNCd9Kyz_yvpYmKmeoWziPpSLb5W3Bb_bZMtb82PWTrRUNCosnflZHK0-9JldkvyyP01xFfq_y211TmysP5CjLXHMc_riinlAssWACI3zMY7mhayEnt-eQO3JYZY8hTuu14Xgca-4hDbvejxhpzb7aj0411sb49JXojU2wMLMXSYxGrxAdrPP6ddz96lLjcgfq9OQP_sBaCQ
&isDarkTheme=true
&platform=android
Here we need to take userid, session id, access token, isDarkTheme, platform, page. 
As soon as he clicks we use the get profile API that fetches the name and all of the user. 
We then show a welcome message saying Hi Name, How may I help you today along with a few chips that the user can use to start the conversation. It could be - fetch my P&L, ledger or a generate query. IN this phase only focusing on 11 reports related APIs and RAG Function. 
The user can also apt to use the chat for free text instead where the user can chat with the bot. 
If the user chooses the chatbot - we redirect to the /chat interface. Where the conversation starts. There we have an agentic AI chatbot that uses claude anthropic sonnet-4-6 for now and then later should be able to toggle between haik if needed in the future from the backend. 
The chatbot has access to tools - which are basically APIs from the backend, it also has a raise a ticket API from freshdesk where we can give an option to raise a ticket to the customer support team with the conversation in the description. I also have the fields to use that I will share below later. Each API is a hardcoded flow where the bot involvement is almost none it only decides the intent. 
If the user answers vaguely to a question and it creates in decision - feel free to ask followup questions. But the cap for followup questions is + 2 (2 follow up questions). And the max conversation cap in a conversation is 10 messages. 
If the issue isn’t resolved within 10 messages - you should ask if the user wants to raise a ticket to the customer support. 
There are 2 ways to interact with the customer support now - one is raise a ticket and the other is to show a small chip / card / modal that basically shows the customer care number and the call timings if the user wants to instantly call. Even after raising a ticket the user should be see a small chip where the user can click and it’s a customer support phone number to call. 
Now since we are relying on the app’s keys and tokens one thing to verify is that - do we keep the 10 conversation cap as the user might have another query which was unrelated to the first. This could be a guardrail where we could add a soft in the prompt along with conversation number like we have page numbers in a book. So we can stop the current conversation and request it to escalate to the user.
Each module will have a separate set of guardrails so I would like to have a structured thing for the prompts and all so I can easily tweak it instead of keeping it in the code files. 
Along with this I would also like to have a conversation store where after every response from the bot we have a separate thread that input the conversation in the PSQL database (Need help deriving the structure of the table too now). 
After that we also need tracing where we can trace every single conversation, decisions, tool calls, etc. So we can finetune a model out of it later for internal use. 
Flow
Main Page - Default message. 
Whenever the user enters the chat interface - like claude says. We’ll put something like
Hey First Name - how can I help you today. 
I can help you fetch your reports, explain processes. Etc. Files land right here in chat - no email verification needed. 
The user then sees 4 chips. PLease keep these chips configurable in a json or some python dictionary or class. 
📊 Get my P&L
📒 Show my ledger
🧾 "How do I check my trade details?"
❓ What are my brokerage charges?
You can refer to the 1a screen in the jini_widget_screens.html. 
The user can either select a chip or write a message. Either ways the first message will be the either chip or the message user inputs. 
This kicks off bot flow. 
Entry 1 — Support Section (generic entry)
Default message (Phase 1, Client ID): (Phase 2, First Name)
Hey X008593 — what do you need?
 I can fetch your reports instantly, explain charges and processes, or check your ticket status. Files land right here in chat — no email verification needed.
That last line is deliberate: "verification required from registered email ID" appears in every single cluster (58 P&L + 14 Holding + 5 Ledger + 9 Contract Note tickets). The bot kills that entire friction category because it's post-login
The 4 chips (data-driven selection):
📊 Get my P&L — highest-volume sub-type (731 tickets) and the top cluster is "difficulty accessing/downloading" — a direct-fulfilment chip
📒 Show my ledger — second-largest access-friction cluster (62 tickets "issues with report downloads")
🧾 "How do I check my trade details?"  —Trade details is 1,525 tickets — it's not just the top Orders sub-type, it's 5x the second-place one (Redemption Status, 299) and bigger than most entire query types. If you get one Orders chip, this is it by sheer volume
❓ What are my brokerage charges? — the explanation-intent chip, routing to the RAG path; validated by your existing Image 1 concept
Input placeholder: "Ask anything about FinX…"
Trust footer: "Factual answers only — never investment advice." (keep from Image 1; it's a compliance guardrail made visible) 
Entry 2 — Reports Screen (intent-based entry)
The customer was already on the Reports screen — skip orientation entirely, open pre-scoped:
Default message:
Which report do you need, X008593?
 Pick one below or just type — I'll deliver it here as PDF or Excel.
The 4 chips (fulfilment only, by ticket volume):
📊 P&L Statement
📒 Ledger
📁 Holding Statement
🧾 Tax Report
Input placeholder rotates the long tail: "or type: CML, Contract Note, Capital Gain, Global…" — this handles sub-types 5–11 without breaking the 4-chip limit. The placeholder teaches what else is possible. 
"What's New ✨" pill (expands on tap)
Collapsed: a small pill top-right of the entry screen: ✨ What's New
Expanded (3 items max):
⚡ 11 reports, instant — P&L, Ledger, Holding, Tax Report + 7 more, delivered in chat as PDF or Excel
🔓 No email verification — you're logged in, so your reports come straight to you
🎫 Tickets — raise a support ticket without leaving chat
Rules: dismissible, reappears only when content changes, never blocks the chips.
Greeting pool (rotate, time-aware)
Default: "Hey X008593 — what do you need?"
Morning (6 am –9am): "Good morning, X008593 ☀️ What can I get for you?"
Market hours: "Hi X008593 — markets are live. Need a report or a quick answer?" (9:15am - 3:30PM)
Post-market: "Hi X008593 👋 Markets are closed — I'm not." (3:30PM - 11:00PM)
P&L Flow
The flow — common spine for both options
Step 1 — Segment selection. Chips: Equity / F&O / Commodity. 
(Customer-facing labels; internally mapped Cash/Derv/Comm — never show "Derv" to a customer, that's internal jargon leaking.)
Step 2 — Date range. Preset chips first, calendar only on "Custom":
This FY · This Month · Last 3 months · Custom range 📅
Presets cover ~80% of requests (your cluster data: "Requesting P&L Reports for Various Periods" — 67 tickets, mostly FY-based) and skip the picker entirely — fastest path.
Step 3 — Confirm + deliver (this is where Screens 1 and 2 diverge).
Option 1 — In-widget file delivery:
Format Available: 📄 PDF / Send a Email
Bot calls API(s) → renders file → delivers as a chat file card (filename, size, format icon, Download/Share buttons)
App: Download + Email buttons on the card.
Caption: "Your Equity P&L for FY 2025-26 (as of 15-Jul-2026, incl. charges)." + the cluster-driven helper: "Trouble opening it? Tell me." → provide option for 
Email
Raise a Ticket
Option 2 — Sent to registered mobile:
No format picker needed in-chat (or keep it, if the sent artefact varies)
Bot confirms: "Done — your Equity P&L for FY 2025-26 is on its way to your registered email ID san***.harsha@gmail,com."
Include expected arrival ("usually within 2 minutes") and a fallback: "Didn't get it? Tell me."
One caution: your #1 ticket cluster is "difficulty accessing/downloading reports" — routing customers out of the widget to another channel re-introduces a failure surface (SMS delays, DND blocks, wrong number on record). Option 2 works best as the web fallback or an explicit customer choice, not the default.
Date picker UX — prevention over correction
The smart move is to make invalid dates unselectable rather than letting the customer pick them and then showing errors:
Calendar hard-disables (greyed, non-tappable): anything before 01-Jan-2018, anything after today+7
Dynamic 2-year clamp: the moment the start date is picked, the calendar visually dims everything beyond start+2 years, with a one-line hint: "Up to [date] — max 2-year range". The customer physically cannot construct an invalid range
Start > end impossible by design: picking an end date earlier than start simply re-anchors it as the new start (standard range-picker behaviour) — no error message ever needed for this
Inline, not modal: the calendar renders inside the chat as a widget card (per your requirement), scoped to the widget — two month-views on app full-screen, one compact month on web floating window
The only error that can still occur is at API level (no data / session expiry / timeout), and those are chat messages, not picker errors
Error display principle: since the picker prevents all input errors, every remaining error is conversational — the bot says it in a message bubble with a recovery chip ("Try a different range" / "Raise a ticket"), never a red toast.
Choice Jini · Tax Report / Capital Gain Flow — AI-Agent-First Specification
Audience: This document is written to be fed directly to Claude Code (or any coding agent) implementing the flow inside the FinX Jini widget (App WebView + Web floating window). It is deterministic where the product owner has decided, and every remaining assumption is explicitly tagged [ASSUMPTION] or [OPEN] so the developer can spot and resolve them without re-reading chat history.
Design spine: This flow reuses the existing Jini patterns already live in Jini_Widget_Screens.html: the P&L stepper card (2a), conversational error bubbles with recovery chips — never toasts (2d), the file-delivery card + "Trouble opening it? Tell me." helper line (1d), and the What's New deep-link behaviour (1c). Do not invent new UI primitives; parametrise the existing ones.

1. Scope & intents
1.1 What this flow does
Generates the client's Tax Report for a chosen financial year and delivers it in-chat as PDF or Excel, or emails both formats to the client's registered email — via POST /api/middleware/GetTaxReportPDF.
1.2 Intent routing (all roads lead here)
User utterance (examples)
Route
Extra behaviour
"tax report", "tax statement", "report for tax filing", "ITR report"
Tax Report flow
—
"capital gain", "capital gains report", "CG statement", "STCG/LTCG report"
Tax Report flow
Prepend CG education line (§4.1) — capital gains are served inside the Tax Report; there is no separate CG API
"tax P&L", "tax pnl"
Tax Report flow
Prepend Tax-P&L education line (§4.1). Do not route to the P&L Statement flow
Tapping the Tax Report chip on Entry 2 · Reports screen (1b)
Tax Report flow
—
What's New CTA "Capital Gain report in Excel" (1a/1b)
Tax Report flow
Drops prefilled prompt "Capital gain report" into input (per 1c UPDATE behaviour) → CG education line applies
"P&L", "profit and loss", "pnl statement" (no "tax" qualifier)
P&L flow (2a) — not this flow
—

Disambiguation rule: the token tax anywhere in a report-type utterance wins over p&l/pnl. capital gain/cg (as a report request) always means Tax Report.

2. Financial-year model (dynamic — no hardcoding)
Indian FY = 1 April → 31 March.
currentFY(today):
  y = today.year
  start = (today.month >= 4) ? y : y - 1
  return f"{start}-{start+1}"          # API format "YYYY-YYYY"

supportedFYs = [ currentFY, currentFY-1, currentFY-2 ]   # exactly 3, computed at runtime
defaultFY    = currentFY - 1                              # last COMPLETED FY — the tax-filing year

Chip labels use short form FY 2025-26; API payload uses long form "2025-2026". Maintain one mapping function; never format twice.
The current (in-progress) FY chip carries the sub-caption "year-to-date" and its file card carries the provisional caption (§6.2).
defaultFY (last completed year) is the visually suggested chip — pre-highlighted, listed first.
On 1 April the window rolls automatically: e.g. from Apr 2027, chips become 2027-28 (YTD) / 2026-27 (default) / 2025-26, and 2024-25 silently drops. No release needed. Product decision: keep this dynamic — do not pin to the three years named in the API doc.

3. Flow — state machine
[INTENT] ──► S0 (education line, CG / tax-P&L intents only)
        └──► S1 · Financial year        chips: FY 2025-26 (default) · FY 2026-27 (year-to-date) · FY 2024-25
                 │  (skipped/pre-confirmed if FY parsed from free text)
                 ▼
             S2 · How do you want it?   chips: 📄 PDF here · 📊 Excel here · ✉️ Email (PDF + Excel)
                 │
                 ├── PDF/Excel here ──► S3a GENERATING ──► S4a FILE CARD ──► S5 post-delivery chips
                 │                          │ (spinner if >5s, per 2d rule)
                 │                          └─ errors → E-* bubbles (§7)
                 │
                 └── Email ──────────► S3b GENERATING ──► S4b EMAIL-SENT CARD ──► S5' didn't-get-it chips
                                            └─ errors → E-* bubbles (§7)

Stepper mechanics (identical to P&L 2a):
Steps render as a single stepper card: 1 · Financial year, 2 · How do you want it?.
Completed steps stay tappable to edit. Tapping a done step re-opens its chips; downstream selections are cleared; nothing is re-fetched until the flow reaches generation again.
All errors are conversational bubbles with recovery chips — never toasts (2d).
If generation exceeds 5 s, show the in-bubble progress line "Generating your Tax Report…" (same threshold as P&L).

4. Copy — every string, verbatim
Placeholders in {braces} are runtime values. Keep the Jini voice: short, warm, factual; footer rule "Factual answers only — never investment advice" continues to apply to the surrounding widget.
4.1 S0 · Education lines (conditional, one bubble, before the stepper)
Trigger intent
Copy
Capital gain
"Quick note — your capital gains are part of the Tax Report, so that's what I'll get you. It has everything you need for filing. 👍"
Tax P&L
"Heads-up — on FinX the Tax P&L is the Tax Report. Same document, one report. Setting it up now."

The education line is informational only; it never asks a question and never blocks S1.
4.2 S1 · Financial year
Prompt: "Sure — which financial year?"
Chips: FY 2025-26 (pre-highlighted, first) · FY 2026-27 · year-to-date · FY 2024-25
Hint line under chips: "Current + last 2 financial years available."
Free-text pre-filled confirm (2c pattern): "Got it — Tax Report for {FY_short}. Confirm?" chips Confirm · Change year
Step summary once done (stepper row): 1 · Financial year — FY 2025-26 ✓
4.3 S2 · Format & delivery (single step, 3 chips — product decision)
Prompt: "How do you want it?"
Chips: 📄 PDF, right here · 📊 Excel, right here · ✉️ Email me both
Sub-caption on the email chip (or as hint line): "PDF + Excel to your registered email."
4.4 S3 · Generating
Immediate ack bubble: "On it — Tax Report for {FY_short}…"
If > 5 s: progress line "Generating your Tax Report…"
4.5 S4a · File card (in-chat delivery)
Reuses the 1d file card, without any password line (Tax Report PDFs/Excels are not password-protected — confirmed).
Lead-in: "Here's your Tax Report for {FY_short}" — for CG intent: "Here's your Tax Report for {FY_short} — capital gains are inside"
Card filename (display name, not the server name — §5.4): Tax_Report_{FY_short_compact}.pdf e.g. Tax_Report_FY2025-26.pdf / .xlsx
Card meta line: {size} · PDF or {size} · Excel — no password segment
Current-FY provisional caption (only when FY == currentFY): "Covers 1 Apr {startYear} – {today, d MMM yyyy} · year-to-date, figures may change till 31 Mar."
Helper line (mandatory after every file delivery, per 1d): "Trouble opening it? Tell me."
4.6 S5 · Post-delivery chips (in-chat delivery)
Rendered under the file card:
Chip
Behaviour
📊 Also get it as Excel (or 📄 Also get it as PDF — the format not just delivered)
Serve from cache if warm (§5.3), else re-call API with the other FileFormat. New file card, same FY.
✉️ Email me both
Runs the email branch (S3b) for the same FY.
🎫 Raise a ticket
Existing ticket flow; ticket references "Tax Report {FY_short}".

4.7 S4b · Email-sent card
"Done — your Tax Report for {FY_short} (PDF + Excel) is on its way to {masked_email}."
Sub-line: "Usually arrives within 2 minutes."
Helper: "Didn't get it? Tell me."
{masked_email} = registered email, masked exactly like the P&L flow (san***.harsha@gmail.com). Not editable in-bot — compliance. If the user asks to send elsewhere: "I can only send reports to your registered email. You can update it from Profile → Contact details, then ask me again."
4.8 S5' · Didn't-get-it chips (email branch)
↺ Resend · 📄 Get it here instead · 🎫 Raise a ticket
Resend → re-run email calls; confirmation: "Re-sent — allow up to 2 minutes."
"Get it here instead" → jumps to S2 with only the two here chips (email chip hidden this pass).
4.9 Trouble-opening flow ("Tell me." tapped after in-chat file)
Tapping sends the literal user message "I can't open the file" (1d behaviour). Jini replies with one bubble:
"Sorry about that — let's fix it. A couple of quick things: • PDF needs any PDF viewer (it's not password-protected). • Excel (.xlsx) opens in Excel, Google Sheets, or WPS. If it still won't open, the file may have come through incomplete — pick an option:"
Recovery chips: ↺ Send it again · {📊 Try Excel instead | 📄 Try PDF instead} (opposite format) · ✉️ Email me both · 🎫 Raise a ticket
Send it again re-calls the API (fresh URL, fresh bytes — §5.3) rather than re-pushing possibly-corrupt cached bytes.
Ticket copy reuses the P&L pattern: "Ticket #{id} raised for this report. Our team will reach out within 24 hours. Track it anytime — just ask 'ticket status'.

6. Edge cases
#
Case
Handling
EC-1
FY parsed from free text is outside the 3-year window
E-YEAR bubble, no API call
EC-2
User asks for AY
Convert AY→FY, explicit confirm before proceeding (§1.3)
EC-3
Current-FY report requested in early April (days of data)
Allowed; provisional caption states the covered range, which makes thin data self-explanatory. If API returns no-data → E-NODATA
EC-4
User taps a completed step to edit FY after a file was delivered
Stepper reopens S1; prior file card stays in history; new generation uses new FY; cache keyed per-FY so no cross-contamination
EC-5
"Also get it as Excel" after cache expiry
Transparent re-call; if it fails, standard error bubbles (never blame the cache in copy)
EC-6
Double-tap / repeat request same FY+format within TTL
Serve from cache; do not double-call the API
EC-7
Session expires mid-flow
E-SESSION — selections persisted; on re-login resume at the step in progress (identical to P&L 2d behaviour)
EC-8
User asks to email to a different address
Refusal copy in §4.7 — registered email only
EC-9
Client has no registered email on file
[OPEN — can this occur?] If yes: hide the email chip in S2 and, if email is requested by text, reply: "There's no email registered on your account yet — add one in Profile → Contact details, or get the file right here." chips 📄 PDF here · 📊 Excel here
EC-10
Widget closed / app killed during generation
On next open within session TTL, if bytes landed in cache, greet with the file card: "Your Tax Report for {FY_short} is ready — here it is." Otherwise nothing resumes automatically [ASSUMPTION]
EC-11
"capital gain for FY 2026-27" free text
Education line + pre-filled FY confirm combine in one turn: education bubble, then "Got it — Tax Report for FY 2026-27 (year-to-date). Confirm?"
EC-12
Email branch: one of the two calls succeeds, the other fails
Tell the truth: "Your PDF is on its way to {masked_email}, but the Excel didn't go through." chips ↺ Retry Excel · 📊 Get Excel here · 🎫 Raise a ticket


7. Error taxonomy — conversational bubbles + recovery chips (never toasts)
Code
Trigger
Bubble copy
Recovery chips
E-NODATA
API failure meaning no data in that FY (the only failure Reason confirmed by product)
"No transactions found for FY {FY_short}, so there's nothing to report for that year."
Try FY {defaultFY} (or another in-window year) · 🎫 Raise a ticket
E-YEAR
Requested FY outside window
"I can pull Tax Reports for the current and last two financial years — that's {list}. Which one?"
The 3 FY chips
E-TIMEOUT
API or byte-fetch exceeds timeout / network failure
"That took longer than it should — the report didn't come through. Your selections are saved."
↺ Retry · 🎫 Raise a ticket
E-FETCH
Status: Success but URL 404s / empty / wrong magic bytes (§5.5)
"The report generated but arrived incomplete on my side — let me redo it." (auto-retry once; if the retry also fails →) "Still not coming through cleanly."
after failed retry: ↺ Try again · ✉️ Email me both · 🎫 Raise a ticket
E-UNKNOWN
Any other Status != "Success"
"Something went wrong generating that report on our side."
↺ Retry · 🎫 Raise a ticket

Rules: user-facing copy never exposes Reason strings, HTTP codes, or URLs. Log Reason verbatim server-side for the [OPEN] failure-taxonomy hardening below. E-FETCH auto-retries once silently before showing the bubble's second line.
Here's the Tax Report / Capital Gain flow in the same format and P&L Report:
Tax Report / Capital Gain Flow
The flow — one spine, three intents (tax report / capital gain / tax P&L)
Step 0 — Intent education (conditional, only for CG and Tax-P&L intents).
Capital gain intent: "Quick note — your capital gains are part of the Tax Report, so that's what I'll get you. It has everything you need for filing."
Tax P&L intent: "Heads-up — on FinX the Tax P&L is the Tax Report. Same document, one report."
(No separate CG API exists — every intent calls GetTaxReportPDF. The education line prevents "where's my CG report?" tickets. Bare "P&L" without "tax" still routes to the P&L flow.)
Step 1 — Financial year. Chips: FY 2025-26 (default, first) / FY 2026-27 · year-to-date / FY 2024-25.
Computed dynamically (current + last 2, Apr–Mar boundary) — rolls forward every 1 April with no release.
Default highlight = last completed FY, since that's the tax-filing year.
Free-text years pre-fill and skip to confirm ("Got it — Tax Report for FY 2025-26. Confirm?"). AY mentions are converted with an explicit confirm ("AY 2026-27 → that's FY 2025-26, correct?"). Out-of-window years get a chip re-prompt, never an API call.
No calendar anywhere — FY replaces the whole date-range step from P&L.
Step 2 — How do you want it? Chips: 📄 PDF here / 📊 Excel here / ✉️ Send Email (PDF & Excel).
Single step, three chips (format + channel merged; email always carries both formats).
Hint under email chip: "PDF + Excel to your registered email."
Step 3 — Generate + deliver (where the two branches diverge).
Option 1 — In-chat file delivery (RequestFor 2, FileFormat 1 or 2):
Bot backend calls API → fetches the returned URL server-side → validates bytes (size floor + magic bytes) → delivers as a chat file card. The unauthenticated URL never reaches the client or logs.
Display name renamed to Tax_Report_FY2025-26.pdf / .xlsx (server name leaks ClientId — never surfaced).
Card meta: "212 KB · PDF" — no password line (these files aren't protected).
Caption: "Here's your Tax Report for FY 2025-26" — CG intent variant: "…— capital gains are inside." Current-FY variant adds: "year-to-date, figures may change till 31 Mar."
Helper after every card: "Trouble opening it? Tell me." → replies with viewer help (any PDF reader / Excel or Google Sheets, no password), then chips:
Send it again (fresh API call, not cache)
Try Excel instead / Try PDF instead (opposite format)
Email me both
Raise a ticket
Post-delivery chips: 📊 Also get it as Excel (served from 15-min cache if warm, no duplicate API call) / ✉️ Email me both / 🎫 Raise a ticket.
If generation exceeds 5s: "Generating your Tax Report…"
Option 2 — Email to registered address (RequestFor 1, two calls: FileFormat 1 + 2):
Middleware sends the mail itself — bot never handles the address.
Bot confirms: "Done — your Tax Report for FY 2025-26 (PDF + Excel) is on its way to san***.harsha@gmail.com."
Expected arrival ("usually within 2 minutes") + fallback: "Didn't get it? Tell me." → chips: ↺ Resend / 📄 Get it here instead / 🎫 Raise a ticket.
Address not editable in-bot; "send to another email" → "I can only send reports to your registered email — update it from Profile → Contact details."
Partial failure (one format sent, one failed): say it honestly — "Your PDF is on its way, but the Excel didn't go through" + retry chips.
Errors — conversational bubbles + recovery chips, never toasts:
No data in FY: "No transactions found for FY 2024-25, so there's nothing to report for that year." → Try FY 2025-26 / 🎫 Raise a ticket
Session expiry: "Your session timed out… Log in again and I'll pick up right where we left off — your selections are saved." → Log in again
Timeout/network: "That took longer than it should — the report didn't come through. Your selections are saved." → ↺ Retry / 🎫 Raise a ticket
Success-but-broken file (URL 404s / 0 bytes / wrong magic bytes): silent auto-retry once, then "The report arrived incomplete on my side…" → ↺ Try again / ✉️ Email me both / 🎫 Raise a ticket
Completed steps stay tappable to edit throughout, same as P&L.
Same content as the spec file, just in this walkthrough shape — want me to fold this format into the document as a front-page summary?

All answers locked in. Here's the Ledger flow in the same step-wise format:
Ledger / MTF Ledger Flow
The flow — one spine, two report types, data API + download API behind one "generate" step
Step 0 — Intent routing (all roads lead here):
Ledger: "ledger", "account statement", "statement of account", "my ledger", "fund statement" → Ledger flow, report type pre-set to Ledger (Step 1 skipped, shown as completed and tappable to edit).
MTF Ledger: "MTF ledger", "margin trading ledger", "MTF statement", "margin funding statement" → report type pre-set to MTF Ledger.
Ambiguous: "statement" alone, or Ledger chip tapped on Entry 2 · Reports screen → Step 1 shown with both chips.
Collision guards: "holding statement" → Holding Statement flow (not here); "contract note" → Contract Note; "tax statement" → Tax Report flow. The word "ledger" or "account statement" wins for this flow; "holding"/"contract"/"tax" qualifiers win for theirs.
Free-text dates in the first message ("ledger from Jan to March") → parse, pre-fill Step 2, jump to confirm (2c pattern).
Step 1 — Report type. Chips: Ledger / MTF Ledger.
Skipped when intent already names the type (still editable as a completed step).
No customer education line needed here — both labels are customer-safe terms.
Step 2 — Date range. Preset chips first, calendar only on Custom:
Chips: Last 3 months · Last FY · Custom range 📅
Calendar rules: floor 1 Jan 2019 (dates older than 2019 hard-disabled), cap = today + 7 days, no max-range clamp — a 2019-to-today range is valid.
Preset chips show resolved dates (V2 style) so "Last FY" is unambiguous: "Last FY · 1 Apr 2025 – 31 Mar 2026".
Free-text out-of-window request ("ledger for 2017"): "I can pull ledger entries from Jan 2019 onwards — records before that aren't available here. Want the earliest possible instead?" → chips Jan 2019 – Dec 2020 / 📅 Pick dates.
Explicit confirm after Custom selection, same as P&L.
Step 3 — How do you want it? Chips: 📄 PDF, right here / ✉️ Send to email.
Two options only — no Excel for ledger.
No in-chat summary card — the deliverable is the PDF, full stop.
Step 4 — Generate + deliver (two API calls behind one step, invisible to the user):
Sequence: data API returns ledger entries → Download API called with the same selection returns the file link → bot backend fetches the PDF server-side → delivers bytes as a chat file card (link never exposed, same security posture as Tax). API-level details are handled in the flow implementation — the spec only fixes the sequence and the user-visible behaviour.
If generation exceeds 5s: "Generating your Ledger…"
Display name: Ledger_1Apr2025-31Mar2026.pdf / MTF_Ledger_... (friendly rename, no client code in filename).
Caption: "Here's your Ledger for 1 Apr 2025 – 31 Mar 2026" / "…your MTF Ledger for…"
Helper after every file card: "Trouble opening it? Tell me." → viewer help (no password on these), then chips: ↺ Send it again (fresh generation) · ✉️ Email it instead · 🎫 Raise a ticket.
Email branch:
Confirmation: "Done — your Ledger for 1 Apr 2025 – 31 Mar 2026 is on its way to san***.harsha@gmail.com." + "Usually arrives within 2 minutes."
Fallback: "Didn't get it? Tell me." → ↺ Resend / 📄 Get it here as PDF / 🎫 Raise a ticket.
Registered email only, masked, not editable — same refusal copy as Tax if user asks to send elsewhere.
Edge cases:
EC-1 · Empty range (Ledger): no entries between selected dates → "No ledger entries found between 14 Apr and 14 Jul 2026, so there's nothing to report there." → chips Try a different range / 🎫 Raise a ticket. Conversational bubble, never a toast.
EC-2 · Empty MTF: user requests MTF Ledger, no MTF activity → plain no-data copy (per your call, no MTF education): "No data available for MTF Ledger in that range." → Try Ledger instead / Try a different range.
EC-3 · Pre-2019 free-text request: handled at Step 2 (see above) — never reaches the API.
EC-4 · Future-heavy range: end date beyond today+7 typed in free text → clamp with confirm: "I can include up to 21 Jul 2026 — set that as the end date?"
EC-5 · Data API succeeds, Download API fails (or link fetch 404s/0-bytes): silent auto-retry of the download step once; if still failing → "The ledger generated but didn't come through cleanly on my side." → ↺ Try again / ✉️ Email it instead / 🎫 Raise a ticket. Never mention the two-API mechanics.
EC-6 · Very large range (2019→today, no clamp exists): allowed; if generation is slow the 5s progress line covers it; consider a soft caption on delivery: "That's a big one — 7 years of entries." Timeout still lands on the standard retry bubble with selections saved.
EC-7 · Session expiry mid-flow: "Your session timed out… your selections are saved." → Log in again, resume at the interrupted step.
EC-8 · Step edit after delivery: completed steps stay tappable; switching Ledger→MTF Ledger clears the date confirm? No — keep the date range, only regenerate (type and range are independent). Prior file card stays in history.
EC-9 · Repeat identical request within the session → serve cached bytes, no duplicate generation; Send it again from the trouble flow always bypasses cache.
EC-10 · "MTF" typed mid-flow ("actually make it MTF") → treated as editing Step 1, range preserved, regenerate.
EC-11 · Range spanning FY boundary (like the sample's Mar 2025 → Jul 2026): fully valid, no special handling or warning.
EC-12 · Email leg fails after data/download succeeded: honest partial-failure copy → ↺ Retry email / 📄 Get it here as PDF / 🎫 Raise a ticket.

Contract Note Flow
The flow — one date step, then the note-list card (the new primitive); per-note PDF/email, bulk = email-all only
Step 0 — Intent routing (all roads lead here):
"contract note(s)", "CN", "ECN", "digital contract note", "trade confirmation", "trade bill", typed "Contract Note" on Entry 2 → this flow.
Free-text dates pre-fill Step 1: "contract note for yesterday" → single-day fetch, no chips shown.
Collision guards: "tax…" → Tax Report; "ledger / account statement / statement of account" → Ledger; "holding statement" → Holding Statement; bare "contract" with no trade context → clarify, never assume.
Step 1 — Date range. Rows with resolved dates: Last trading day · Mon, 13 Jul / Last 7 days / This month / Custom range 📅.
Calendar: floor 1 Jan 2018, cap today (notes exist only for completed trading days — no +7d), no max range.
Hint line: "From Jan 2018 · up to today · no range limit."
Step 2 — Fetch & branch (data API → body StatusCode, never HTTP status):
204 → no-data bubble (EC-1).
1 note → skip list, deliver directly (3c).
2+ notes → note-list card (3b): "Found 38 contract notes between 12 May and 13 Jul 2026 — tap any to get it here." Rows = day + weekday, month dividers, segment badge only on dual-note days (Grp1 → "Equity & F&O", MCX → "Commodity"; no other groups exist), no invoice numbers. 10 rows per page + Show more (N remaining). Footer chips: ✉️ Email all N / 📅 Change dates. Page size and all thresholds are remote-config.
> 50 notes (config): narrow-nudge before rendering the list — "That's 312 notes — want to narrow it down, or should I email them all?" → ✉️ Email all 312 / 📅 Narrow the range.
Step 3 — Per-note delivery (row tap or single-note case):
Download API called with file_id → returns URL → bot backend fetches bytes server-side → file card in chat. URL/file_id never exposed; no token expiry, so rows stay tappable indefinitely within the session.
Card: Contract_Note_13Jul2026.pdf (+ _MCX suffix for the commodity note) · 96 KB · PDF — no password line.
Mandatory helper: "Trouble opening it? Tell me." → reply confirms it's not password-protected, viewer help, then ↺ Try again / ✉️ Email it instead / 🎫 Raise a ticket.
Post-delivery chips: ✉️ Email this note / 📅 Other dates.
Step 4 — Email branch (single or bulk):
"Done — 38 contract notes (12 May – 13 Jul 2026) are on their way to san***.harsha@gmail.com. Usually arrives within 2 minutes."
"Didn't get it? Tell me." → ↺ Resend / 📄 Get one here instead / 🎫 Raise a ticket.
Registered email only, masked, not editable. No download-all exists — bulk is email-only by design.
Edge cases — final:
EC-1 · 204 no-data: "No contract notes between {from} and {to} — notes are only generated for days you traded." → Try a different range / 🎫 Raise a ticket. The explainer clause is mandatory — this is usually a no-trade period, not a failure.
EC-3 · Today before generation: "Today's note isn't ready yet — it's usually generated by end of day. I can get yesterday's right now." → Get yesterday's / 📅 Pick dates. [OPEN — exact publish time; plug in when known]
EC-4 · Dual-note day (Grp1 + MCX): two rows, segment badges; keyed by file_id — never dedupe by date/id (shared on 09-06 in the sample).
EC-5 · Big range: narrow-nudge at the config threshold; list itself paginates at 10.
EC-6 · Download fails after list OK (404 / 0 bytes / wrong magic bytes): one silent retry, then the incomplete-file bubble → ↺ Try again / ✉️ Email it instead / 🎫 Raise a ticket. Two-API mechanics never mentioned.
EC-7 · Pre-2018 typed: "I can pull contract notes from Jan 2018 onwards…" → earliest-range chip / 📅 Pick dates. Calendar hard-disables it, so only free-text hits this.
EC-8 · Future date typed: "Contract notes exist only for completed trading days — latest I can get is Mon, 13 Jul." → Last trading day.
EC-9 · Ambiguous free-text day ("note for the 5th"): assume current month if ≤ today else previous month, with explicit confirm.
EC-10 · Invoice-number request ("send contract note 399834"): invoice numbers aren't surfaced or searchable — ask for the trade date instead: "Which date is that for? I fetch notes by day."
EC-13 · Repeat tap on same row: cached bytes within session TTL; no duplicate download call.
EC-14 · Step edit after deliveries: 📅 Change dates reopens Step 1; delivered file cards stay in history.

Brokerage
This is not flow. We need to call this API on the intent click or Free Text 

Edge cases
EC-1 · API failure / timeout: "Couldn't fetch your brokerage details just now." → ↺ Retry / 🎫 Raise a ticket. One silent retry first; never a toast.
EC-4 · Segment not in the plan ("what's my MF / SLB brokerage?"): "Your plan covers Equity, Derivatives, Commodity and Currency — here they are." + card → 🎫 Raise a ticket for the rest.
EC-5 · Calculation ask: per Q3 — rate + contract-note pointer, no computed rupee figure [Do not compute, just show brokerage details].
EC-6 · "Why was I charged ₹57?" — that's a ledger/bill dispute, not plan info: show the relevant rate row, then route → Show my ledger / 🎫 Raise a ticket.
EC-7 · PDF/email requested ("email me my brokerage"): "Brokerage details live right here — there's no document for this one." + card. No file path exists by design.
EC-8 · Repeat intent in-session: cached render, no duplicate API call.
EC-10 · Stale plan after a plan change mid-session: cache is session-scoped only; fresh session = fresh fetch. No longer-lived cache.
CML Flow
The flow — no steps at all: intent → API → PDF in chat. PDF only.
Step 0 — Intent routing (all roads lead here):
"CML", "CML copy", "client master list", "client master report", "my demat account details document", "KYC copy for transfer" → CML flow.
Typed "CML" from the Entry 2 hint line ("or type: CML, Contract Note, Capital Gain…") → here.
Step 1 — Generate + deliver (single step, nothing to ask the user):
On intent, immediately: call API → read body.cmlLink → backend fetches the bytes within seconds (the signed URL expires in 120s — treat it as single-use: fetch immediately, discard the URL, never cache it, never log it, never send it to the client).
If generation exceeds 5s: "Getting your CML…"
Ack + card: "Here's your Client Master List ✓" / Client_Master_List.pdf (matches the server's own disposition filename — keep it; unlike other flows it contains nothing sensitive) / {size} · PDF — no password line [ASSUMPTION — confirm CML PDFs are unprotected].
Mandatory helper: "Trouble opening it? Tell me." → viewer help, then chips: ↺ Send it again / 🎫 Raise a ticket. Send it again OR Send Email always re-calls the API — the old URL is long dead; only byte-cache may be reused, never the link.
Post-delivery chip (high-frequency follow-up): Something incorrect in it? 🎫 Raise a ticket — CML requests are very often followed by "my address/bank/nominee is wrong", which is a service request, not a re-download.

Global Detail Report Flow
Global Detail Report Flow — final
The flow — discovered mainly through P&L, not searched for by name; Equity/Derivative → dates → PDF here or email
Step 0 — Intent routing & discovery:
Primary path — discovery inside P&L: users don't know the term "Global Report", so the P&L flow advertises it at two natural moments: (a) after a P&L delivery, post-delivery chip 📑 Scrip-wise detail (Global Report) — carries the P&L's segment and dates across as pre-filled, editable steps; (b) during P&L back-and-forth — when a user asks for something the P&L doesn't show ("show me trade-wise breakup", "which scrips did I trade", "charges breakup with trades"), Jini offers: "That level of detail lives in the Global Detail Report — want it for the same period?" → Yes, get it / No, stay with P&L.
Direct utterances (rare but claimed): "global report", "global detail report", "detail report", "scrip-wise report", "trade summary", "security-wise summary" → straight in.
Collision guards: bare "P&L" always → P&L flow; "ledger/account statement" → Ledger; "contract note" → Contract Note. "Scrip-wise P&L" → P&L flow first, with the during-flow Global offer above doing the redirect if detail is what they wanted.
Free-text company code or dates pre-fill their steps and skip to confirm.
Step 1 — Company code. Chips: Equity / Derivative.
Exactly two options, no "Both". Always asked when not stated in free text — no silent default (unlike FY flows, there's no majority case).
Pre-filled (still editable) only when arriving via the post-P&L chip, mapped from the P&L segment.
Step 2 — Date range. Chips with resolved dates: This Month · 1 – 14 Jul / Last 3 months · 14 Apr – 14 Jul / Last FY · 1 Apr 2025 – 31 Mar 2026 / Custom range 📅.
Floor 1 Jan 2018 (hard-disabled below), cap today + 7 days, no max range. Explicit confirm on Custom.
Step 3 — How do you want it? Chips: 📄 PDF, right here / ✉️ Send to email. PDF only — no Excel.
Step 4 — Generate + deliver (two-API sequence like Ledger, invisible to the user):
Data API → Download API returns the file link → backend fetches bytes server-side → file card in chat. Link never exposed, never logged, discarded after fetch.
Progress past 5s: "Generating your Global Detail Report…"
Card: Global_Detail_Report_Equity_1Apr2025-31Mar2026.pdf · {size} · PDF — no password line (confirmed unprotected; trouble-opening copy says so).
Caption: "Here's your Global Detail Report — Equity, 1 Apr 2025 – 31 Mar 2026" + mandatory "Trouble opening it? Tell me." → viewer help, then ↺ Send it again (fresh generation, bypasses cache) / ✉️ Email it instead / 🎫 Raise a ticket.
Post-delivery chips: Get Derivative too (other code, same dates — one tap) / ✉️ Email it / 📅 Change dates.
Email branch — spec'd as bot-sends (backend downloads via the Download API, then emails through its own mail service), consistent with Ledger since the download step already exists; if middleware later exposes a send-flag à la Tax's RequestFor: 1, it's a drop-in swap with no copy change. Registered email only, masked, not editable. Confirmation: "Done — your Global Detail Report (Equity, 1 Apr 2025 – 31 Mar 2026) is on its way to san***.harsha@gmail.com. Usually arrives within 2 minutes." → "Didn't get it? Tell me." → ↺ Resend / 📄 Get it here as PDF / 🎫 Raise a ticket.
Edge cases — final:
EC-1 · No trades in range for the selected code: "No Derivative trades found between 1 and 14 Jul 2026, so there's nothing to report there." → Try Equity / Try a different range / 🎫 Raise a ticket. The cross-code chip is mandatory — segment-siloed traders hit this constantly.
EC-2 · Trade-less but expense/opening-bearing range: report-worthy — generate normally (confirmed).
EC-3 · Pre-2018 typed: "I can pull this report from Jan 2018 onwards…" → earliest-range chip / 📅 Pick dates (calendar already hard-disables it).
EC-4 · End date beyond today+7: clamp with explicit confirm — "I can include up to 21 Jul — set that as the end date?"
EC-5 · Huge range (2018→today): allowed, no clamp; slow generation covered by the 5s progress line; timeout → standard retry bubble, selections saved.
EC-6 · Generation OK, fetch fails / broken bytes (404, 0 bytes, wrong magic): one silent retry with fresh generation → "The report generated but arrived incomplete on my side." → ↺ Try again / ✉️ Email it instead / 🎫 Raise a ticket. Two-API mechanics never surface.
EC-8 · Completed-step edits: Equity↔Derivative keeps dates and regenerates; date change keeps the code; prior cards stay in history.
EC-9 · Repeat identical request in-session: cached bytes (15-min TTL); Send it again and Resend bypass cache.
EC-10 · "As Excel please": "This one comes as a PDF only — here it is." + / 🎫 Raise a ticket.
EC-11 · Mid-flow pivot to P&L ("actually just give me the P&L"): clean hand-off carrying segment + dates where valid; P&L's 2-year clamp may truncate a longer range — if it does, say so explicitly ("P&L covers up to 2 years at a time — I've set 14 Jul 2024 – 14 Jul 2026") rather than silently trimming.
EC-12 · Email leg fails after generation: honest copy → ↺ Retry email / 📄 Get it here as PDF / 🎫 Raise a ticket.
EC-13 · Reverse pivot from P&L (the designed path): post-P&L chip and during-flow offer carry segment+dates in; if the P&L range violates nothing here (it can't — this flow's window is a superset), no re-confirm needed beyond the normal step summaries.

Rest opf the flow follows the similar design as that, except contract note - that would follow contract note flow screens.html. 

