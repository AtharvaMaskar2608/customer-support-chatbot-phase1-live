## ADDED Requirements

### Requirement: Flow and step state-machine types

The system SHALL define the flow/step state-machine types the engine drives:
`FlowState` (the current flow's intent, current step, collected parameters, and
cache key), `Step` (an `id`, a `kind` — segment / date_range / fy / delivery /
format / confirm / generate — a display `state`, and its chips), and the
transition types between steps. Fulfilment SHALL be deterministic; the LLM SHALL
NOT improvise the fulfilment path once the intent is known.

#### Scenario: Flow state carries collected params

- **WHEN** a flow advances through its steps
- **THEN** `FlowState` SHALL carry the intent, the current step, and the parameters collected so far, sufficient for the engine to resume deterministically

#### Scenario: Step kind drives the render block

- **WHEN** a step is presented
- **THEN** its `kind` SHALL determine which render block the engine emits (e.g. `date_range` → calendar, `segment` → chip row)

### Requirement: Per-flow date windows differ by design

The system SHALL define per-flow date-window configuration and SHALL NOT unify it
across flows. The configured floors, caps, and max-range clamps SHALL be:

- P&L — floor `2018-01-01`, cap `today+7`, max range 2 years.
- Ledger — floor `2019-01-01`, cap `today+7` [CONFIRM], no max range.
- Contract Note — floor `2018-01-01`, cap `today`, no max range.
- Global Detail — floor `2018-01-01`, no max range (BLOCKED flow; window recorded for completeness).
- Tax Report — FY-based (current + last two FYs), not a date range.

The values SHALL be sourced from remote config so calendar bounds are tunable; the
engine SHALL hard-disable out-of-range dates in the calendar rather than validate
after selection.

#### Scenario: P&L clamps to a two-year range

- **WHEN** a P&L date range start is chosen
- **THEN** the calendar SHALL disable dates beyond start+2 years, and the floor `2018-01-01` and cap `today+7` SHALL bound the pickable range

#### Scenario: Contract-note cap is today, ledger floor is 2019

- **WHEN** the engine configures the contract-note vs ledger calendars
- **THEN** the contract-note cap SHALL be `today` (floor `2018-01-01`) and the ledger floor SHALL be `2019-01-01`, reflecting the per-flow difference

### Requirement: Financial-year helpers computed dynamically

The system SHALL **implement** (not merely type) the financial-year helpers in the
contracts layer (`app/contracts/flow.py`), as pure date math shared by the flow
engine, the tax flow, and the router, so the Apr-1 rollover logic exists once. They
SHALL compute the FY window dynamically and SHALL NOT hardcode the three years.
`currentFY(today)` SHALL return `"YYYY-YYYY"` where the start year is `today.year`
when `today.month >= 4` else `today.year - 1`. `supportedFYs` SHALL be `[currentFY,
currentFY-1, currentFY-2]`. `defaultFY` SHALL be `currentFY-1` (the last completed
FY), pre-highlighted and listed first. A single mapping function SHALL convert
between the short chip form (`FY 2025-26`) and the API long form (`"2025-2026"`).
AY→FY conversion SHALL require explicit user confirmation.

#### Scenario: FY window rolls on 1 April

- **WHEN** `currentFY` is computed on or after 1 April
- **THEN** the start year SHALL be the current calendar year, and `supportedFYs` SHALL roll forward so the oldest year drops without a code change

#### Scenario: Default FY is the last completed year

- **WHEN** the tax flow presents FY chips
- **THEN** `defaultFY` SHALL be `currentFY-1`, pre-highlighted and listed first

### Requirement: Byte validation with silent retry

The system SHALL define byte-validation semantics applied before every file
delivery: a size floor and magic-byte check (`%PDF` for PDF, `PK` zip header for
Excel). On validation failure the engine SHALL perform exactly one silent
auto-retry with a fresh generation, and only if the retry also fails SHALL it
surface the `E-FETCH` error bubble.

#### Scenario: Magic bytes checked before delivery

- **WHEN** the backend fetches report bytes for delivery
- **THEN** the engine SHALL verify the size floor and magic bytes, and SHALL NOT emit a `file_card` for bytes that fail validation

#### Scenario: One silent retry then E-FETCH

- **WHEN** byte validation fails
- **THEN** the engine SHALL retry generation once silently, and only on a second failure SHALL it emit the `E-FETCH` error bubble

### Requirement: Per-flow selection and byte cache

The system SHALL define a per-flow byte/selection cache with a 15-minute TTL,
session-scoped and keyed per selection so edits do not cross-contaminate. Explicit
"send it again" / "resend" requests SHALL bypass the cache and force a fresh
fetch.

#### Scenario: Cache keyed per selection

- **WHEN** a user edits a completed step and changes a selection
- **THEN** the cache key SHALL change so the prior selection's cached bytes are not reused

#### Scenario: Resend bypasses cache

- **WHEN** the user asks to "send it again" or "resend"
- **THEN** the engine SHALL bypass the cache and fetch fresh bytes regardless of the 15-minute TTL

### Requirement: Flow registration via module-level FLOW and discovery

The system SHALL define the flow-registration contract as a `FlowSpec` protocol.
Each flow module SHALL expose a module-level `FLOW: FlowSpec` object and SHALL NOT
import a registration function or edit any shared file. The engine's importlib
discovery (in `app/flows/__init__.py`, owned by flow-engine-runtime) SHALL collect
each module's `FLOW`, keyed by its `Intent`. There SHALL be no registration imports
and no hand-maintained shared registry list.

#### Scenario: A flow is discovered by its module-level FLOW

- **WHEN** the engine's importlib discovery runs over `app/flows/`
- **THEN** each module's module-level `FLOW: FlowSpec` SHALL be collected and keyed by its `Intent`, with no registration import and no edit to a shared registry file
