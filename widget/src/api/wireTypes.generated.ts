/**
 * GENERATED — do not edit by hand.
 * Source: app/contracts/schema/chat_wire.schema.json (frozen contract).
 * Regenerate: npm run gen:types
 */
/**
 * The typed chip-action set. A chip action is sufficient for the backend to
 * advance a flow deterministically, without free-text parsing.
 */
export type ChipActionKind =
  | 'send_text'
  | 'select_param'
  | 'open_calendar'
  | 'raise_ticket'
  | 'call_support'
  | 'retry'
  | 'email'
  | 'show_more'
  | 'deep_link';
export type Message = string | null;
export type AccessToken = string;
export type EntrySurface = 'support' | 'reports';
export type IsDarkTheme = boolean;
export type Page = string;
export type Platform = string;
export type SessionId = string;
export type UserId = string;
export type ThreadId = string | null;
export type TurnNumber = number;
export type ComplianceFooter = boolean;
export type Text = string;
export type Type = 'bubble';
export type Text1 = string;
export type Type1 = 'user_bubble';
export type Label = string;
export type Chips = Chip[];
export type Type2 = 'chip_row';
export type Chips1 = Chip[];
export type Id = string;
export type SelectedLabel = string | null;
export type StepState = 'pending' | 'active' | 'done';
export type Title = string;
export type Steps = StepperStep[];
export type Type3 = 'stepper_card';
export type From = string | null;
export type To = string | null;
export type DisabledRanges = DateRange[];
export type MaxDate = string;
export type MaxRangeDays = number | null;
export type MinDate = string;
export type Type4 = 'calendar';
export type Actions = Chip[];
export type Filename = string;
export type Format = 'pdf' | 'xlsx';
export type Helper = string;
export type PasswordHint = string | null;
export type SizeLabel = string;
export type Type5 = 'file_card';
export type FooterChips = Chip[];
export type MonthDividers = string[];
export type PageSize = number;
export type DateLabel = string;
export type Downloadtoken = string;
export type SegmentBadge = string | null;
export type Weekday = string;
export type Rows = NoteRow[];
export type Total = number;
export type Type6 = 'note_list_card';
export type Label1 = string;
export type Value = string;
export type List = DataRow[];
export type Title1 = string;
export type Groups = DataGroup[];
export type Type7 = 'data_card';
export type Chips2 = Chip[];
/**
 * The five conversational error codes (exactly five).
 */
export type ErrorCode = 'E-NODATA' | 'E-YEAR' | 'E-TIMEOUT' | 'E-FETCH' | 'E-UNKNOWN';
export type Text2 = string;
export type Type8 = 'error_bubble';
export type Chips3 = Chip[];
export type Message1 = string;
export type TicketId = string;
export type Type9 = 'ticket_confirmation';
export type Message2 = string;
export type Type10 = 'generating';
export type Blocks = (
  | Bubble
  | UserBubble
  | ChipRow
  | StepperCard
  | Calendar
  | FileCard
  | NoteListCard
  | DataCard
  | ErrorBubble
  | TicketConfirmation
  | Generating
)[];
export type FollowUpsUsed = number;
export type MessagesCap = number;
export type MessagesUsed = number;
export type EntryChips = Chip[];
export type Greeting = string;
export type FollowUpCap = number;
export type MessageCap = number;
export type NoteThreshold = number;
export type PageSize1 = number;
export type Body = string;
export type Icon = string;
export type MinAppVersion = string | null;
export type Title2 = string;
export type WhatsNew = WhatsNewItem[];
export type ConversationState = 'greeting' | 'collecting' | 'generating' | 'delivered' | 'error' | 'escalated';
/**
 * Every intent the router can classify an utterance into (frozen: exactly 16).
 *
 * Eleven report-flow intents + five non-report intents. ``report_holding`` and
 * ``report_global_detail`` are classifiable but BLOCKED (no captured
 * file-delivery endpoint) — the orchestrator returns a not-yet-available
 * message rather than attempting fulfilment.
 */
export type Intent =
  | 'report_pnl'
  | 'report_ledger'
  | 'report_mtf_ledger'
  | 'report_contract_notes'
  | 'report_tax'
  | 'report_capital_gain'
  | 'report_tax_pnl'
  | 'report_cml'
  | 'report_brokerage'
  | 'report_holding'
  | 'report_global_detail'
  | 'rag_qa'
  | 'raise_ticket'
  | 'ticket_status'
  | 'call_support'
  | 'smalltalk_fallback';
export type ThreadId1 = string;
export type TurnNumber1 = number;

/**
 * Root that references the whole wire contract so a single JSON Schema dump
 * captures the request/response envelopes and the render-block union for the
 * widget's TypeScript codegen.
 */
export interface _WireSchemaRoot {
  request: ChatRequest;
  response: ChatResponse;
}
/**
 * One user turn. Carries the SessionContext, the user action (free text OR a
 * chip action), the thread_id (absent on the first turn), and the turn_number.
 */
export interface ChatRequest {
  action?: ChipAction | null;
  message?: Message;
  session: SessionContext;
  thread_id?: ThreadId;
  turn_number?: TurnNumber;
}
export interface ChipAction {
  kind: ChipActionKind;
  payload?: Payload;
}
export interface Payload {
  [k: string]: string;
}
/**
 * Typed session context derived from the app-handoff URL query params.
 *
 * ``session_id`` and ``access_token`` are both retained (different FinX
 * backends require different credentials) but are excluded from serialization —
 * they SHALL NOT be echoed to the widget in any response body or render block.
 */
export interface SessionContext {
  access_token: AccessToken;
  entry_surface: EntrySurface;
  is_dark_theme?: IsDarkTheme;
  page: Page;
  platform: Platform;
  session_id: SessionId;
  user_id: UserId;
}
/**
 * One complete turn's response (non-streaming). ``config_slice`` is present
 * only on the first (session-seed) response.
 */
export interface ChatResponse {
  blocks: Blocks;
  caps: Caps;
  config_slice?: ConfigSlice | null;
  conversation_state: ConversationState;
  intent?: Intent | null;
  thread_id: ThreadId1;
  turn_number: TurnNumber1;
}
export interface Bubble {
  compliance_footer?: ComplianceFooter;
  text: Text;
  type?: Type;
}
export interface UserBubble {
  text: Text1;
  type?: Type1;
}
export interface ChipRow {
  chips: Chips;
  type?: Type2;
}
export interface Chip {
  action: ChipAction;
  label: Label;
}
/**
 * Editable multi-step card. Completed steps stay tappable: reopening a done
 * step clears downstream selections; the prior file card stays in history and
 * nothing is re-fetched until generation.
 */
export interface StepperCard {
  steps: Steps;
  type?: Type3;
}
export interface StepperStep {
  chips?: Chips1;
  id: Id;
  selected_label?: SelectedLabel;
  state: StepState;
  title: Title;
}
/**
 * In-chat date picker. Out-of-range dates are hard-disabled (the engine
 * disables them rather than validating after selection).
 */
export interface Calendar {
  disabled_ranges?: DisabledRanges;
  max_date: MaxDate;
  max_range_days?: MaxRangeDays;
  min_date: MinDate;
  type?: Type4;
}
/**
 * A ``from``/``to`` date range lifted from an utterance.
 */
export interface DateRange {
  from?: From;
  to?: To;
}
/**
 * A delivered report file. Carries only display-safe fields — NO report URL,
 * file_id, cmlLink, or server filename. For CML the display filename is the
 * server's own ``Client_Master_List.pdf``; for every other flow it is renamed so
 * it does not leak the Client ID.
 */
export interface FileCard {
  actions?: Actions;
  filename: Filename;
  format: Format;
  helper?: Helper;
  password_hint?: PasswordHint;
  size_label: SizeLabel;
  type?: Type5;
}
export interface NoteListCard {
  footer_chips?: FooterChips;
  month_dividers?: MonthDividers;
  page_size?: PageSize;
  rows: Rows;
  total?: Total;
  type?: Type6;
}
/**
 * One contract-note row. Carries an opaque, session-scoped ``downloadToken``
 * as its download handle — NEVER the FinX ``file_id`` (the contract-note
 * endpoints enforce no authentication). The segment badge shows only on
 * dual-note days.
 */
export interface NoteRow {
  date_label: DateLabel;
  downloadToken: Downloadtoken;
  segment_badge?: SegmentBadge;
  weekday: Weekday;
}
/**
 * Dynamic card (brokerage / holding). Iterates whatever the API returns; no
 * hardcoded segment names or row counts, no computed rupee figures.
 */
export interface DataCard {
  groups: Groups;
  type?: Type7;
}
export interface DataGroup {
  list: List;
  title: Title1;
}
/**
 * A ``{label, value}`` row. ``value`` is rendered VERBATIM — the wire type
 * does not reshape or numerically parse it (e.g. brokerage ``desc`` is
 * pre-formatted rate text).
 */
export interface DataRow {
  label: Label1;
  value: Value;
}
/**
 * Conversational error (never a toast). Copy never exposes Reason strings,
 * HTTP codes, or URLs.
 */
export interface ErrorBubble {
  chips?: Chips2;
  code: ErrorCode;
  text: Text2;
  type?: Type8;
}
export interface TicketConfirmation {
  chips?: Chips3;
  message: Message1;
  ticket_id: TicketId;
  type?: Type9;
}
/**
 * Latency indicator emitted when a turn is expected to exceed five seconds.
 */
export interface Generating {
  message?: Message2;
  type?: Type10;
}
export interface Caps {
  follow_ups_used: FollowUpsUsed;
  messages_cap: MessagesCap;
  messages_used: MessagesUsed;
}
/**
 * The client-relevant config delivered in the first ``/api/chat`` response.
 *
 * Carries ONLY entry chips, the greeting, the client-facing limits, and
 * ``whats_new``. Server-only config (RAG tunables, per-flow calendar-bound math,
 * Freshdesk field mapping) is NEVER included here.
 */
export interface ConfigSlice {
  entry_chips: EntryChips;
  greeting: Greeting;
  limits: ClientLimits;
  whats_new?: WhatsNew;
}
/**
 * The client-facing subset of the runtime limits (no server-only knobs).
 */
export interface ClientLimits {
  follow_up_cap: FollowUpCap;
  message_cap: MessageCap;
  note_threshold: NoteThreshold;
  page_size: PageSize1;
}
export interface WhatsNewItem {
  body: Body;
  cta?: Chip | null;
  icon: Icon;
  min_app_version?: MinAppVersion;
  title: Title2;
}
