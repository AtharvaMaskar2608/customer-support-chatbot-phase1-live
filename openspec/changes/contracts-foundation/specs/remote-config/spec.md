## ADDED Requirements

### Requirement: Runtime limits are remote-config

The system SHALL define a `RemoteConfig` schema whose `limits` section carries the
tunable runtime limits with these Phase-1 defaults: contract-note page size 10,
narrow-nudge note threshold 50, conversation message cap 10, and per-ambiguity
follow-up cap 2. These SHALL be sourced from config so they change without a
redeploy.

#### Scenario: Limits sourced from config

- **WHEN** the widget or engine needs a page size, note threshold, message cap, or follow-up cap
- **THEN** it SHALL read the value from `RemoteConfig.limits` rather than a hardcoded constant

### Requirement: Per-surface chip sets

The system SHALL define chip sets per entry surface. The support entry SHALL carry
the four "Popular right now" starter chips; the reports entry SHALL carry the four
fulfilment chips (P&L Statement, Ledger, Holding Statement, Tax Report) plus the
rotating placeholder that teaches the long tail ("or type: CML, Contract Note,
Capital Gain, Global…"). Chip sets SHALL be config-driven and shared across both
entries where applicable.

#### Scenario: Reports entry exposes four chips plus placeholder

- **WHEN** the reports-screen entry is rendered
- **THEN** it SHALL present the four fulfilment chips and the rotating long-tail placeholder from config

### Requirement: Time-aware greeting pool

The system SHALL define a greeting pool with time-aware variants (default,
morning 06:00–09:00, market hours 09:15–15:30, post-market 15:30–23:00), each a
template carrying the `{client_id}` placeholder (Phase-1 greets by Client ID).
The pool SHALL be config-driven and rotate.

#### Scenario: Market-hours greeting selected

- **WHEN** a session starts between 09:15 and 15:30
- **THEN** the greeting SHALL be drawn from the market-hours variant with the Client ID substituted

### Requirement: What's New entries

The system SHALL define a `whats_new` config carrying at most three items, each
with an icon, title, body, an optional CTA (which may deep-link a prefilled
prompt), and an optional `min_app_version`. The schema SHALL support a 24-hour
cache and a per-client-code red-dot badge; entries SHALL never auto-popup.

#### Scenario: At most three items

- **WHEN** `whats_new` is configured
- **THEN** the schema SHALL accept no more than three items, each with an optional `min_app_version` gate

### Requirement: Product list and compliance footer

The system SHALL define a product/report list mapping report types to
customer-facing labels, and the compliance footer text ("Factual answers only —
never investment advice."). Both SHALL be config-driven.

#### Scenario: Compliance footer sourced from config

- **WHEN** a bot bubble sets its compliance-footer flag
- **THEN** the footer text SHALL be read from config

### Requirement: Per-flow calendar bounds are remote-config

The system SHALL carry the per-flow date-window values (floors, caps, max-range
clamps) in remote config so the flow engine reads calendar bounds from config
rather than hardcoding them. The values SHALL remain per-flow (not unified),
matching the flow-engine contract.

#### Scenario: Calendar bounds read from config

- **WHEN** the flow engine configures a calendar for a flow
- **THEN** it SHALL read that flow's floor, cap, and max-range from `RemoteConfig`, and the values SHALL differ per flow

### Requirement: RAG tunables

The system SHALL carry the RAG retrieval tunables in the remote-config schema so
the "all limits are remote-config" rule holds: `rag_candidate_k` (default 25),
`rrf_k` (default 60), `rag_context_k` (default 5), and `reranker` (default
`"none"`). These SHALL be server-only config and SHALL NOT be sent to the widget
in the session-seed config slice.

#### Scenario: RAG tunables read from config

- **WHEN** the RAG service retrieves and fuses candidates
- **THEN** it SHALL read `rag_candidate_k`, `rrf_k`, `rag_context_k`, and `reranker` from `RemoteConfig`, not from hardcoded constants

#### Scenario: RAG tunables are server-only

- **WHEN** the client-facing config slice is built for the widget
- **THEN** it SHALL NOT include the RAG tunables

### Requirement: Freshdesk field mapping is not in remote-config

The remote-config schema SHALL NOT carry the Freshdesk ticket-field mapping; that
mapping is ticketing-owned config at `app/ticketing/freshdesk.yaml` (per `04` §5).
The remote-config schema SHALL remain focused on widget/limits/chips/greeting/
whats_new/products/calendar-bounds/RAG-tunables.

#### Scenario: Ticket mapping lives with ticketing

- **WHEN** the ticket-builder constructs a Freshdesk ticket
- **THEN** it SHALL read the field mapping from `app/ticketing/freshdesk.yaml`, not from the frozen remote-config schema
