## ADDED Requirements

### Requirement: Session bootstrap from URL parameters

The system SHALL expose a session-bootstrap contract that accepts the app-handoff
URL query parameters — `userId` (Client ID, e.g. `X008593`), `sessionId`,
`accessToken` (SSO JWT), `isDarkTheme`, `platform`, and `page` — and produces a
typed `SessionContext` carrying those values plus the resolved `entry_surface`
(support entry vs reports entry). The `sessionId` and `accessToken` SHALL both be
retained, because different FinX backends require different credentials. The
`accessToken` and `sessionId` SHALL NOT be serialized into any render block or
returned to the widget in a response body.

#### Scenario: All six params present

- **WHEN** the widget calls bootstrap with `userId`, `sessionId`, `accessToken`, `isDarkTheme`, `platform`, and `page`
- **THEN** the system SHALL construct a `SessionContext` exposing `user_id`, `session_id`, `access_token`, `is_dark_theme`, `platform`, `page`, and `entry_surface`, and SHALL NOT echo `session_id` or `access_token` in the response payload

#### Scenario: Entry surface derived from page

- **WHEN** the `page` parameter indicates the reports screen
- **THEN** `SessionContext.entry_surface` SHALL be `reports` (otherwise `support`), and the bootstrap response SHALL carry the entry-surface-appropriate greeting and starter chips

### Requirement: Session-seed config delivery

The widget's only network surface SHALL be `POST /api/chat`. The system SHALL NOT
expose a separate remote-config endpoint for the widget. The first chat response
(the session seed) SHALL embed a typed `config_slice` carrying only the
client-relevant config: the entry chips, the time-aware greeting, the
client-facing limits, and `whats_new`. Server-only config (per-flow calendar-bound
math, RAG tunables, Freshdesk field mapping) SHALL NOT be included in `config_slice`.

#### Scenario: First response carries the config slice

- **WHEN** the widget makes its first `/api/chat` call for a session
- **THEN** the response SHALL include a `config_slice` with entry chips, greeting, client-facing limits, and `whats_new`, and the widget SHALL NOT make any other network call to obtain config

#### Scenario: Server-only config is not leaked

- **WHEN** the `config_slice` is serialized
- **THEN** it SHALL NOT contain RAG tunables, per-flow calendar-bound internals, or Freshdesk field mapping

### Requirement: Chat turn request/response envelope

The system SHALL define `POST /api/chat` as the single per-turn endpoint. The
request SHALL carry the `SessionContext`, the user action (free text or a chip
action), the `thread_id` (absent on the first turn), and the `turn_number`. The
response SHALL be a single JSON object containing `thread_id`, `turn_number`, an
ordered array `blocks` of typed render blocks, the detected `intent` (nullable),
the current `conversation_state`, and a `caps` object reporting
`messages_used`, `messages_cap`, and `follow_ups_used`.

#### Scenario: First turn has no thread_id

- **WHEN** a chat request arrives with no `thread_id`
- **THEN** the system SHALL treat it as the first turn, mint a `thread_id`, and return it in the response for the widget to send on subsequent turns

#### Scenario: Response blocks are ordered

- **WHEN** the system returns a chat response
- **THEN** `blocks` SHALL be an ordered array that the widget renders top-to-bottom in array order

### Requirement: Non-streaming one-response-per-turn protocol

The system SHALL deliver exactly one JSON response per user turn (Phase-1
non-streaming decision). The system SHALL NOT use token streaming, SSE, or
server-push for chat turns. When a turn's processing exceeds five seconds, the
response contract SHALL support a `generating` indicator block so the widget can
show a "Generating…" affordance.

#### Scenario: Single response per turn

- **WHEN** a user turn is processed
- **THEN** the system SHALL return exactly one response object containing the complete ordered block array for that turn

#### Scenario: Long-running turn indicator

- **WHEN** turn processing is expected to exceed five seconds
- **THEN** the contract SHALL permit a `generating` block carrying an indicator message

### Requirement: Render-block type taxonomy

The system SHALL define a discriminated render-block union keyed on `type`,
covering every block the widget can display: `bubble` (bot text, with a
compliance-footer flag), `user_bubble` (echoed user text), `chip_row` (quick-reply
chips), `stepper_card` (editable multi-step card), `calendar` (in-chat date picker
with hard-disabled ranges), `file_card` (delivered report file), `note_list_card`
(paginated contract-note list), `data_card` (dynamic card e.g. brokerage/holding),
`error_bubble` (conversational error + recovery chips), `ticket_confirmation`
(raised-ticket card), and `generating` (latency indicator). Every block SHALL be
independently serializable and carry only display-safe fields.

#### Scenario: Block type discriminated on `type`

- **WHEN** the system emits any render block
- **THEN** the block SHALL carry a `type` field whose value is one of the eleven defined block types, and the widget SHALL dispatch on that value

#### Scenario: No sensitive identifiers in blocks

- **WHEN** the system serializes a `file_card`, `note_list_card`, or `data_card`
- **THEN** the block SHALL NOT contain report URLs, `file_id` values, `cmlLink` values, server filenames, or raw registered email — only display-safe rendered fields

### Requirement: Chip action contract

The system SHALL define a `chip_row` whose chips each carry a display `label` and
a typed `action` with payload. The action set SHALL include at least:
`send_text`, `select_param` (segment/FY/format/delivery selection),
`open_calendar`, `raise_ticket`, `call_support`, `retry`, `email`, `show_more`
(pagination), and `deep_link` (prefilled prompt). A chip action SHALL be
sufficient for the backend to advance a flow without free-text parsing.

#### Scenario: Chip carries a typed action

- **WHEN** the system emits a `chip_row`
- **THEN** each chip SHALL carry a `label` and a typed `action` with the payload needed to advance the flow deterministically

### Requirement: Stepper-card edit semantics

The system SHALL define a `stepper_card` whose steps each carry an `id`, `title`,
`state` (`pending` / `active` / `done`), an optional `selected_label`, and the
chips for that step. Completed steps SHALL remain tappable to edit. The contract
SHALL record that tapping a done step reopens it and clears downstream selections,
the prior file card stays in history, and nothing is re-fetched until generation.

#### Scenario: Completed step remains editable

- **WHEN** a `stepper_card` has a step in state `done`
- **THEN** that step SHALL remain tappable, and reopening it SHALL clear downstream step selections without re-fetching until the flow reaches generation again

### Requirement: File-card contract

The system SHALL define a `file_card` carrying a display filename, a size label, a
format (`pdf` / `xlsx`), an optional password hint (e.g. "PAN"), a helper line
("Trouble opening it? Tell me."), and the available actions (download / share /
email). For CML the display filename SHALL be the server's own
`Client_Master_List.pdf`; for all other flows the display filename SHALL be a
renamed value that does not leak the Client ID.

#### Scenario: CML filename carve-out

- **WHEN** the system emits a `file_card` for a CML report
- **THEN** the display filename SHALL be `Client_Master_List.pdf`

#### Scenario: Other reports rename the file

- **WHEN** the system emits a `file_card` for any non-CML report
- **THEN** the display filename SHALL NOT contain the Client ID or the server's original filename

### Requirement: Note-list-card contract

The system SHALL define a `note_list_card` for contract notes. Each row SHALL
carry an **opaque, session-scoped `downloadToken`** as its download handle, and
SHALL NOT carry the FinX `file_id`. The backend SHALL resolve `downloadToken` →
`file_id` server-side; the `file_id` SHALL never reach the client or logs (the
contract-note endpoints enforce no authentication — FLAG A, `03` §7). Each row
SHALL also carry a date label, weekday, and an optional segment badge shown only
on dual-note days (`Grp1` → "Equity & F&O", `MCX` → "Commodity"). The card SHALL
carry `page_size` (default 10), `total`, month dividers, and footer chips
(email-all, change-dates). The page size and the narrow-nudge threshold (default
50) SHALL be sourced from remote config.

#### Scenario: Rows carry an opaque download token, not file_id

- **WHEN** the system builds a `note_list_card`
- **THEN** each row SHALL carry an opaque session-scoped `downloadToken` that the backend resolves to a `file_id` server-side, and the `file_id` SHALL NOT appear anywhere in the serialized card

#### Scenario: Segment badge only on dual-note days

- **WHEN** a trading day has two notes in different segments
- **THEN** the rows for that day SHALL show a segment badge; single-note days SHALL show no badge

### Requirement: Data-card contract renders dynamically

The system SHALL define a `data_card` that renders an array of groups, each with a
`title` and a `list` of `{label, value}` rows, where `value` is rendered
**verbatim** (the wire type SHALL NOT force reshaping or numeric parsing —
brokerage `desc` is pre-formatted rate text like "₹0.10 for trade value of 10
thousand"). For brokerage the card SHALL iterate whatever the API returns and
SHALL NOT hardcode segment names or row counts, and SHALL NOT compute any rupee
figure.

#### Scenario: Verbatim value text

- **WHEN** the system builds a brokerage `data_card`
- **THEN** each row SHALL be `{label, value}` with `value` rendered exactly as returned by the API, with no computed rupee value, no numeric reshaping, and no hardcoded segment list

### Requirement: Error-bubble and ticket-confirmation blocks

The system SHALL define an `error_bubble` carrying an error `code` (from the error
taxonomy), the user-facing copy, and recovery chips, and a `ticket_confirmation`
carrying the ticket id and confirmation message. The call-support chip SHALL
remain available even after a ticket is raised.

#### Scenario: Error bubble is conversational, not a toast

- **WHEN** the system reports an error to the user
- **THEN** it SHALL emit an `error_bubble` with recovery chips, never a toast, and the copy SHALL NOT expose `Reason` strings, HTTP codes, or URLs
