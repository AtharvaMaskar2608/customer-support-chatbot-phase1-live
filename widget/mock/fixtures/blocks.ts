// One typed fixture per frozen wire block type. Copy is drawn from the
// prototype screens in docs/prototype/screens/* so each block matches its
// visual acceptance reference. These fixtures are:
//   1. rendered directly by the block unit tests (T7/T8), and
//   2. composed by the mock server (server.ts) into turn responses.
// Every fixture is validated against the frozen JSON schema by fixtures.test.ts.
import type {
  BubbleBlock,
  UserBubbleBlock,
  ChipRowBlock,
  StepperCardBlock,
  CalendarBlock,
  FileCardBlock,
  NoteListCardBlock,
  DataCardBlock,
  ErrorBubbleBlock,
  TicketConfirmationBlock,
  GeneratingBlock,
  NoteRow,
} from '../../src/api/wireTypes';

export const bubble: BubbleBlock = {
  type: 'bubble',
  text: 'Sure — let’s pull your P&L. First, which segment?',
};

export const complianceBubble: BubbleBlock = {
  type: 'bubble',
  text: 'I give factual answers only — never investment advice.',
  compliance_footer: true,
};

export const userBubble: UserBubbleBlock = {
  type: 'user_bubble',
  text: 'Get my P&L',
};

export const chipRow: ChipRowBlock = {
  type: 'chip_row',
  chips: [
    { label: '📊 Get my P&L', action: { kind: 'send_text', payload: { text: 'Get my P&L', intent: 'report_pnl' } } },
    { label: '📒 Show my ledger', action: { kind: 'send_text', payload: { text: 'Show my ledger', intent: 'report_ledger' } } },
    { label: '🧾 “How do I check my trade details?”', action: { kind: 'send_text', payload: { text: 'How do I check my trade details?', intent: 'rag_qa' } } },
    { label: '❓ What are my brokerage charges?', action: { kind: 'send_text', payload: { text: 'What are my brokerage charges?', intent: 'report_brokerage' } } },
  ],
};

export const stepperCard: StepperCardBlock = {
  type: 'stepper_card',
  steps: [
    {
      id: 'segment',
      title: '1 · Segment',
      state: 'active',
      chips: [
        { label: 'Equity', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'segment', value: 'Equity' } } },
        { label: 'F&O', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'segment', value: 'F&O' } } },
        { label: 'Commodity', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'segment', value: 'Commodity' } } },
      ],
    },
    { id: 'period', title: '2 · Date range', state: 'pending' },
    { id: 'format', title: '3 · How do you want it?', state: 'pending' },
  ],
};

export const calendar: CalendarBlock = {
  type: 'calendar',
  min_date: '2018-01-01',
  max_date: '2026-07-16',
  max_range_days: null,
  disabled_ranges: [{ from: '2026-07-17', to: '2026-07-31' }],
};

export const fileCard: FileCardBlock = {
  type: 'file_card',
  filename: 'PnL_Equity_FY2025-26.pdf',
  size_label: '196 KB',
  format: 'pdf',
  password_hint: 'password: PAN',
  helper: 'Trouble opening it? Tell me.',
  actions: [
    { label: 'Download', action: { kind: 'deep_link', payload: { action_token: 'dl-pnl-eq-fy2526' } } },
    { label: 'Email', action: { kind: 'email', payload: { action_token: 'em-pnl-eq-fy2526' } } },
  ],
};

export const cmlFileCard: FileCardBlock = {
  type: 'file_card',
  filename: 'Client_Master_List.pdf',
  size_label: '9 KB',
  format: 'pdf',
  password_hint: null,
  helper: 'Trouble opening it? Tell me.',
  actions: [
    { label: 'Download', action: { kind: 'deep_link', payload: { action_token: 'dl-cml' } } },
    { label: 'Email', action: { kind: 'email', payload: { action_token: 'em-cml' } } },
  ],
};

const NOTE_ROWS: NoteRow[] = [
  { date_label: 'Mon, 14 Jul 2026', weekday: 'Monday', downloadToken: 'nt-01' },
  { date_label: 'Fri, 11 Jul 2026', weekday: 'Friday', segment_badge: 'NSE·BSE', downloadToken: 'nt-02a' },
  { date_label: 'Fri, 11 Jul 2026', weekday: 'Friday', segment_badge: 'MCX', downloadToken: 'nt-02b' },
  { date_label: 'Wed, 9 Jul 2026', weekday: 'Wednesday', downloadToken: 'nt-03' },
  { date_label: 'Thu, 3 Jul 2026', weekday: 'Thursday', downloadToken: 'nt-04' },
  { date_label: 'Wed, 2 Jul 2026', weekday: 'Wednesday', downloadToken: 'nt-05' },
  { date_label: 'Tue, 1 Jul 2026', weekday: 'Tuesday', downloadToken: 'nt-06' },
  { date_label: 'Fri, 27 Jun 2026', weekday: 'Friday', downloadToken: 'nt-07' },
  { date_label: 'Wed, 25 Jun 2026', weekday: 'Wednesday', downloadToken: 'nt-08' },
  { date_label: 'Mon, 23 Jun 2026', weekday: 'Monday', downloadToken: 'nt-09' },
  { date_label: 'Thu, 18 Jun 2026', weekday: 'Thursday', downloadToken: 'nt-10' },
  { date_label: 'Tue, 16 Jun 2026', weekday: 'Tuesday', downloadToken: 'nt-11' },
];

export const noteListCard: NoteListCardBlock = {
  type: 'note_list_card',
  page_size: 10,
  total: NOTE_ROWS.length,
  month_dividers: ['July 2026', 'June 2026'],
  rows: NOTE_ROWS,
  footer_chips: [
    { label: '✉️ Email all 12', action: { kind: 'email', payload: { action_token: 'em-notes-all' } } },
    { label: '📅 Change dates', action: { kind: 'open_calendar', payload: { flow: 'contract_notes' } } },
  ],
};

export const brokerageCard: DataCardBlock = {
  type: 'data_card',
  groups: [
    { title: 'Equity', list: [
      { label: 'Intraday', value: '₹0.10 for trade value of 10 thousand' },
      { label: 'Delivery', value: '₹1.00 for trade value of 10 thousand' },
    ] },
    { title: 'Derivative', list: [
      { label: 'Stock Future', value: '₹20.00 for trade value of 10 thousand' },
      { label: 'Stock Option', value: '₹20.00 per order' },
    ] },
    { title: 'Commodity', list: [{ label: 'Futures', value: '₹20.00 for trade value of 10 thousand' }] },
    { title: 'Currency', list: [{ label: 'Options', value: '₹20.00 per order' }] },
  ],
};

export const holdingCard: DataCardBlock = {
  type: 'data_card',
  groups: [
    { title: 'Your holdings · LTP · P&L', list: [
      { label: 'RELIANCE-EQ', value: 'Qty 50 · Avg ₹1,297.38 · LTP ₹1,303.30 · +₹296.00' },
      { label: 'TCS-EQ', value: 'Qty 20 · Avg ₹3,402.10 · LTP ₹3,180.50 · −₹4,432.00' },
      { label: 'INFY-EQ', value: 'Qty 40 · Avg ₹1,498.20 · LTP ₹1,560.75 · +₹2,502.00' },
      { label: 'HDFCBANK-EQ', value: 'Qty 30 · Avg ₹1,655.00 · LTP ₹1,642.90 · −₹363.00' },
    ] },
  ],
};

export const errorBubble: ErrorBubbleBlock = {
  type: 'error_bubble',
  code: 'E-NODATA',
  text: 'No P&L found for that period — you may not have traded then. Want to pick a different range?',
  chips: [
    { label: '📅 Pick another range', action: { kind: 'open_calendar', payload: { flow: 'pnl' } } },
    { label: '🎫 Raise a ticket', action: { kind: 'raise_ticket', payload: {} } },
  ],
};

export const timeoutErrorBubble: ErrorBubbleBlock = {
  type: 'error_bubble',
  code: 'E-TIMEOUT',
  text: 'That took longer than expected and timed out. Want to try again?',
  chips: [{ label: '↺ Retry', action: { kind: 'retry', payload: {} } }],
};

export const ticketConfirmation: TicketConfirmationBlock = {
  type: 'ticket_confirmation',
  ticket_id: '#48211',
  message: 'Our team will reach out within 24 hours. Track it anytime — just ask ‘ticket status’.',
  chips: [{ label: '📞 Call support instead', action: { kind: 'call_support', payload: {} } }],
};

export const generating: GeneratingBlock = {
  type: 'generating',
  message: 'Generating…',
};

/** Every block fixture keyed by its wire `type` (used by fixtures.test.ts). */
export const ALL_BLOCK_FIXTURES = {
  bubble,
  user_bubble: userBubble,
  chip_row: chipRow,
  stepper_card: stepperCard,
  calendar,
  file_card: fileCard,
  note_list_card: noteListCard,
  data_card: brokerageCard,
  error_bubble: errorBubble,
  ticket_confirmation: ticketConfirmation,
  generating,
} as const;

// Referenced by demos/tests to avoid unused-export lint on the extra variants.
export const EXTRA_FIXTURES = { complianceBubble, cmlFileCard, holdingCard, timeoutErrorBubble } as const;
