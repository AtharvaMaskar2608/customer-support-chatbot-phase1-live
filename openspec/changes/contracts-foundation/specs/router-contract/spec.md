## ADDED Requirements

### Requirement: Complete Intent enum

The system SHALL define a single frozen `Intent` enum that the router classifies
every utterance into. It SHALL contain the eleven report-flow intents plus five
non-report intents. No downstream change SHALL add, remove, or rename Intent
values. The eleven report intents SHALL be:

- `report_pnl` — P&L Statement (`GetGlobalPNLPDF`)
- `report_ledger` — Ledger (`GetLedgerDetailsPDF`, `Margin:0`)
- `report_mtf_ledger` — MTF Ledger (`GetLedgerDetailsPDF`, `Margin:1` [CONFIRM])
- `report_contract_notes` — Contract Notes (list + per-note download)
- `report_tax` — Tax Report (`GetTaxReportPDF`)
- `report_capital_gain` — Capital Gain (routes to the Tax flow; prepend CG education line)
- `report_tax_pnl` — Tax P&L (routes to the Tax flow; prepend Tax-P&L education line)
- `report_cml` — CML (`/mis/reports/generate`)
- `report_brokerage` — Brokerage slab card (`get-brokerage-slab`)
- `report_holding` — Holding Statement (BLOCKED: no captured file-delivery endpoint)
- `report_global_detail` — Global Detail / Detailed P&L (BLOCKED: no captured file-delivery endpoint)

The five non-report intents SHALL be: `rag_qa`, `raise_ticket`, `ticket_status`,
`call_support`, and `smalltalk_fallback`.

#### Scenario: Enum enumerates all sixteen intents

- **WHEN** the router classifies any utterance
- **THEN** the result SHALL be one of the sixteen defined `Intent` values

#### Scenario: Blocked intents are classifiable but not fulfillable

- **WHEN** the router classifies an utterance as `report_holding` or `report_global_detail`
- **THEN** the intent SHALL be returned as a valid enum value, and the orchestrator SHALL respond with a not-yet-available message and escalation chips rather than attempting fulfilment

#### Scenario: Capital-gain and tax-pnl route to the tax flow

- **WHEN** the router returns `report_capital_gain` or `report_tax_pnl`
- **THEN** the result SHALL carry an education-line marker, and the flow engine SHALL drive the Tax Report flow (there is no separate Capital Gain API)

### Requirement: Intent precedence rules

The system SHALL encode deterministic intent-precedence rules so ambiguous
utterances resolve consistently. The token `tax` anywhere in a report-type
utterance SHALL win over `p&l`/`pnl`. `capital gain`/`cg` as a report request
SHALL always mean the Tax Report (`report_capital_gain`). `holding statement`
SHALL resolve to `report_holding`, not `report_ledger`. Bare `p&l`/`pnl` with no
`tax` qualifier SHALL resolve to `report_pnl`. `ledger`/`account statement` SHALL
win for the ledger flow over `holding`/`contract`/`tax` qualifiers except where
those qualifiers are present.

#### Scenario: Tax beats P&L

- **WHEN** an utterance contains both `tax` and `p&l`
- **THEN** the router SHALL classify it as a tax-flow intent, not `report_pnl`

#### Scenario: Holding statement is not the ledger

- **WHEN** an utterance says "holding statement"
- **THEN** the router SHALL classify it as `report_holding`, not `report_ledger`

### Requirement: Extracted parameters

The system SHALL define `ExtractedParams` carrying the parameters the router
lifts from free text: `fy` (a financial-year value), `date_range`
(`from`/`to`), `segment`, `report_format`, and `delivery`. `segment` SHALL be a
customer-facing `Segment` enum (`equity`, `fno`, `commodity`); the mapping of
`Segment` to per-backend API group vocabularies SHALL NOT live in the router
contract. `report_format` SHALL be a `ReportFormat` enum (`pdf`, `excel`).
`delivery` SHALL distinguish in-chat delivery from email. All fields SHALL be
optional (absent when not present in the utterance).

#### Scenario: Segment stays customer-facing

- **WHEN** the router extracts a segment
- **THEN** `ExtractedParams.segment` SHALL be a `Segment` enum value (`equity`/`fno`/`commodity`), never an internal API group string like `Cash`/`Derv`/`Comm`

#### Scenario: Parameters are optional

- **WHEN** an utterance contains no date, FY, segment, or format
- **THEN** `ExtractedParams` SHALL carry those fields as absent, and the flow engine SHALL collect them via stepper chips

### Requirement: Router result fields and follow-up cap

The system SHALL define a frozen `RouterResult` carrying: `intent`,
`extracted_params`, `needs_confirmation` (true for the AY→FY case that requires
explicit user confirmation), `follow_up_question` (nullable — the disambiguation
prompt when genuinely ambiguous), `detected_language` (for the sticky-language
rule), `escalate` (true when the follow-up cap is reached and the flow must go to
ticket/call), and `education_line` (nullable — the capital-gain / tax-P&L
education prefix). The router SHALL emit a `follow_up_question` ONLY when genuinely
ambiguous; the follow-up count per disambiguation is capped (default 2, sourced
from remote config), and at the cap `escalate` SHALL be true rather than the router
guessing.

#### Scenario: No follow-up when unambiguous

- **WHEN** the router has enough information to classify and fulfil
- **THEN** `RouterResult.follow_up_question` SHALL be null and `escalate` SHALL be false

#### Scenario: Follow-up cap sets escalate

- **WHEN** the follow-up count for a disambiguation reaches the configured cap
- **THEN** `RouterResult.escalate` SHALL be true (routing to raise-ticket / call-support) instead of a further guess

#### Scenario: AY input requires confirmation

- **WHEN** the user supplies an assessment year that must be converted to a financial year
- **THEN** `RouterResult.needs_confirmation` SHALL be true so the flow confirms the FY before fetching

### Requirement: Conversation context input

The system SHALL define a frozen `ConversationContext` that is the input to the
router and the orchestrator pipeline. It SHALL carry the session bootstrap fields
(`user_id`, `session_id`, `access_token`, `is_dark_theme`, `platform`, `page`),
references to the turn history, the `turn_number`, the `follow_up_count` for the
current disambiguation, and the sticky-language state. `session_id` and
`access_token` SHALL NOT be serialized to the client.

#### Scenario: Context carries follow-up and language state

- **WHEN** the router is invoked for a turn
- **THEN** it SHALL receive a `ConversationContext` exposing the turn history references, `turn_number`, `follow_up_count`, and sticky-language state needed to decide follow-ups and language

### Requirement: RAG answer and retrieved-chunk contract types

The system SHALL define frozen RAG contract types in a contracts module
(`app/contracts/rag.py`): `RetrievedChunk` (chunk id, chunk text, source/entry id,
vector score, FTS rank, fused score), `RagAnswer` (answer text, citations →
chunk ids, a refusal flag with a refusal-reason enum, and the `retrieval_context`),
and the canonical `retrieval_context` shape as a `list[str]`. These SHALL be the
single shared shapes used by rag-service, the orchestrator, the conversation-store
writer, and tracing, none of which import `app/rag/`.

#### Scenario: retrieval_context is a list of strings

- **WHEN** any component records or persists retrieval context
- **THEN** it SHALL use the canonical `retrieval_context: list[str]` shape defined in the contracts, not a component-local shape

#### Scenario: RagAnswer carries citations and a refusal flag

- **WHEN** the RAG service produces an answer
- **THEN** `RagAnswer` SHALL carry the answer text, citations referencing `RetrievedChunk` ids, and a refusal flag with a refusal-reason enum

### Requirement: Raise-ticket tool contract

The system SHALL define the `raise_ticket` and `get_ticket_status` tools (in the
frozen tool-definition module `app/contracts/tools.py`) that the orchestrator
invokes: `raise_ticket` takes the Client ID, the query type, and the conversation
transcript reference and returns the ticket id and status; `get_ticket_status`
takes a ticket reference and returns its status. The Freshdesk field mapping used
to build the ticket SHALL be sourced from ticketing-owned config
(`app/ticketing/freshdesk.yaml`, per `04` §5), not hardcoded and not part of the
frozen remote-config schema.

#### Scenario: Ticket tool inputs are typed

- **WHEN** the orchestrator raises a ticket
- **THEN** it SHALL call the `raise_ticket` tool with a schema-validated input (Client ID, query type, transcript reference) and receive a typed result carrying the ticket id

### Requirement: Routing via forced tool use

The router SHALL classify by issuing exactly ONE Claude call with `tools=[route]`
and a forced tool choice
(`tool_choice={"type":"tool","name":"route","disable_parallel_tool_use":true}`).
The `route` tool's `input_schema` SHALL be generated from `RouterResult`, and the
`RouterResult` SHALL materialize directly from the API-validated `tool_use.input`.
Because `strict: true` makes the tool input API-schema-validated, the contract
SHALL NOT include any malformed-JSON repair or re-ask step. On API/transport
failure only, the router SHALL return `RouterResult(intent=smalltalk_fallback,
escalate=True)`. The deterministic post-layers (intent precedence, FY computation,
sticky-language) SHALL run unchanged on the materialized result.

#### Scenario: Router forces the route tool

- **WHEN** the router classifies an utterance
- **THEN** it SHALL make one Claude call with `tools=[route]` and `tool_choice` forcing the `route` tool with `disable_parallel_tool_use: true`, and `RouterResult` SHALL be built from the `tool_use.input`

#### Scenario: No JSON-repair path

- **WHEN** the route tool returns its input
- **THEN** the contract SHALL rely on the API-enforced (`strict: true`) schema, with no malformed-JSON repair or re-ask step

#### Scenario: Transport failure falls back

- **WHEN** the Claude call fails at the API/transport layer
- **THEN** the router SHALL return `RouterResult(intent=smalltalk_fallback, escalate=True)`

### Requirement: Agent tool definitions

The system SHALL define the complete frozen tool set as native Anthropic tool
definitions (`name`, `description`, `input_schema`) in `app/contracts/tools.py`,
each carrying a **top-level `strict: true`** (GA, no beta header). The frozen tool
names SHALL be: `route`, `get_pnl_report`, `get_ledger_report` (carrying an `mtf`
flag), `get_contract_notes`, `get_tax_report`, `get_cml`, `get_brokerage_slabs`,
`search_kb`, `raise_ticket`, and `get_ticket_status`. Every `input_schema` SHALL be
generated from the frozen Pydantic models via `model_json_schema()` and SHALL set
`additionalProperties: false` and a full `required` list, so the API guarantees
`tool_use.input` validates exactly. Each `input_schema` SHALL stay within the
structured-outputs-supported JSON Schema subset — no recursive schemas, no numeric
`minimum`/`maximum`/`multipleOf`, no string `minLength`/`maxLength`, no complex
array constraints; the Pydantic schema generation strips or avoids those, and any
such constraint SHALL be enforced in application/validation code after receipt, not
by the tool's `input_schema`. The generated schemas SHALL be dumped to a checked-in
`app/contracts/schema/tools.schema.json` with a drift test. The tool NAME strings
SHALL be frozen; implementations bind at runtime via the orchestrator's registry
(implementations live in the engine / rag / ticketing changes — this change ships
definitions only).

#### Scenario: Tool set is frozen and schema-generated

- **WHEN** the tool definitions are built
- **THEN** the ten tool names SHALL be exactly `route`, `get_pnl_report`, `get_ledger_report`, `get_contract_notes`, `get_tax_report`, `get_cml`, `get_brokerage_slabs`, `search_kb`, `raise_ticket`, `get_ticket_status`, each with `strict: true` and an `input_schema` generated from its Pydantic model

#### Scenario: Tool schema drift is caught

- **WHEN** a frozen model changes without regenerating `tools.schema.json`
- **THEN** the drift test SHALL fail

#### Scenario: Names frozen, implementations bind at runtime

- **WHEN** a flow / rag / ticketing change implements a tool
- **THEN** it SHALL bind its implementation to the frozen tool name via the orchestrator registry, and SHALL NOT edit the frozen `app/contracts/tools.py` definitions
