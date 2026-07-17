// Mock implementation of the POST /api/chat wire contract. This is the SINGLE
// source of mock truth: the vitest suite drives it through MSW (test/msw.ts)
// and the Vite `mock` mode drives it through an in-process middleware
// (vitePlugin.ts), so dev/E2E and tests never diverge. Real backend wiring is
// Wave 2 (conversation-orchestrator); this file has no FinX/Freshdesk surface.
import type {
  ChatRequest,
  ChatResponse,
  Block,
  ChipAction,
  StepperCardBlock,
  Chip,
  ConversationState,
} from '../src/api/wireTypes';
import * as fx from './fixtures/blocks';
import { buildConfigSlice } from './fixtures/config';

type PnlSelections = { segment?: string; period?: string; format?: string };
interface ThreadState {
  clientId: string;
  messagesUsed: number;
  pnl: PnlSelections;
}

const threads = new Map<string, ThreadState>();
let threadSeq = 0;

/** Reset all mock state — call between tests. */
export function resetMock(): void {
  threads.clear();
  threadSeq = 0;
}

function response(
  threadId: string,
  turn: number,
  blocks: Block[],
  state: ConversationState,
  st: ThreadState,
  configSlice?: ChatResponse['config_slice'],
): ChatResponse {
  return {
    thread_id: threadId,
    turn_number: turn,
    blocks,
    conversation_state: state,
    caps: { messages_used: st.messagesUsed, messages_cap: 10, follow_ups_used: 0 },
    ...(configSlice ? { config_slice: configSlice } : {}),
  };
}

// ---- P&L stepper -----------------------------------------------------------

const PERIOD_CHIPS: Chip[] = [
  { label: 'This FY', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'period', value: 'This FY' } } },
  { label: 'This Month', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'period', value: 'This Month' } } },
  { label: 'Last 3 months', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'period', value: 'Last 3 months' } } },
  { label: 'Custom range 📅', action: { kind: 'open_calendar', payload: { flow: 'pnl' } } },
];
const FORMAT_CHIPS: Chip[] = [
  { label: 'PDF', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'format', value: 'PDF' } } },
  { label: 'Excel', action: { kind: 'select_param', payload: { flow: 'pnl', step: 'format', value: 'Excel' } } },
];
const SEGMENT_CHIPS: Chip[] = fx.stepperCard.steps[0].chips!;

function buildPnlStepper(sel: PnlSelections): StepperCardBlock {
  const segmentActive = !sel.segment;
  const periodActive = !!sel.segment && !sel.period;
  const formatActive = !!sel.period && !sel.format;
  return {
    type: 'stepper_card',
    steps: [
      {
        id: 'segment',
        title: '1 · Segment',
        state: sel.segment ? 'done' : 'active',
        selected_label: sel.segment ?? null,
        chips: segmentActive ? SEGMENT_CHIPS : [],
      },
      {
        id: 'period',
        title: '2 · Date range',
        state: sel.period ? 'done' : sel.segment ? 'active' : 'pending',
        selected_label: sel.period ?? null,
        chips: periodActive ? PERIOD_CHIPS : [],
      },
      {
        id: 'format',
        title: '3 · How do you want it?',
        state: sel.format ? 'done' : sel.period ? 'active' : 'pending',
        selected_label: sel.format ?? null,
        chips: formatActive ? FORMAT_CHIPS : [],
      },
    ],
  };
}

function pnlPrompt(sel: PnlSelections): string {
  if (!sel.segment) return 'Sure — let’s pull your P&L. First, which segment?';
  if (!sel.period) return `Got it — ${sel.segment}. What period?`;
  if (!sel.format) return 'And how do you want it?';
  return 'Here’s your P&L 👇';
}

function advancePnl(st: ThreadState, threadId: string, turn: number, payload: Record<string, string>): ChatResponse {
  const sel = st.pnl;
  const step = payload.step as keyof PnlSelections;
  const label = payload.value ?? '';
  // Reopen (edit): tapping a done step clears it + all downstream selections.
  if (payload.reopen === '1') {
    if (step === 'segment') st.pnl = {};
    else if (step === 'period') st.pnl = { segment: sel.segment };
    else if (step === 'format') st.pnl = { segment: sel.segment, period: sel.period };
    return response(
      threadId,
      turn,
      [{ type: 'bubble', text: pnlPrompt(st.pnl) }, buildPnlStepper(st.pnl)],
      'collecting',
      st,
    );
  }
  // Forward selection.
  if (step === 'segment') st.pnl = { segment: label };
  else if (step === 'period') st.pnl = { ...sel, period: label };
  else if (step === 'format') st.pnl = { ...sel, format: label };

  const userEcho: Block = { type: 'user_bubble', text: label };
  if (st.pnl.segment && st.pnl.period && st.pnl.format) {
    const delivery: Block = {
      type: 'chip_row',
      chips: [
        { label: '📑 Scrip-wise detail (Global Report)', action: { kind: 'send_text', payload: { text: 'Scrip-wise detail', intent: 'report_global_detail' } } },
        { label: '✉️ Email it', action: { kind: 'email', payload: { action_token: 'em-pnl' } } },
        { label: '🎫 Raise a ticket', action: { kind: 'raise_ticket', payload: {} } },
      ],
    };
    return response(threadId, turn, [userEcho, { type: 'bubble', text: pnlPrompt(st.pnl) }, fx.fileCard, delivery], 'delivered', st);
  }
  return response(threadId, turn, [userEcho, { type: 'bubble', text: pnlPrompt(st.pnl) }, buildPnlStepper(st.pnl)], 'collecting', st);
}

// ---- intent routing --------------------------------------------------------

function intentBlocks(intent: string, echo: string): { blocks: Block[]; state: ConversationState } {
  const user: Block = { type: 'user_bubble', text: echo };
  switch (intent) {
    case 'report_pnl':
      return { blocks: [user, { type: 'bubble', text: pnlPrompt({}) }, fx.stepperCard], state: 'collecting' };
    case 'report_contract_notes':
      return { blocks: [user, { type: 'bubble', text: 'Here are your contract notes — tap any day to download.' }, fx.noteListCard], state: 'delivered' };
    case 'report_brokerage':
      return { blocks: [user, { type: 'bubble', text: 'Here’s your brokerage plan 👇' }, fx.brokerageCard], state: 'delivered' };
    case 'report_holding':
      return { blocks: [user, { type: 'bubble', text: 'Holdings change with the market — this reflects prices as of the last refresh, not a point-in-time statement.' }, fx.holdingCard], state: 'delivered' };
    case 'raise_ticket':
      return { blocks: [user, fx.ticketConfirmation], state: 'escalated' };
    case 'rag_qa':
      return { blocks: [user, { type: 'bubble', text: 'You can check trade details under Reports → Contract Notes, or ask me for a specific date.', compliance_footer: true }], state: 'delivered' };
    default:
      return { blocks: [user, { type: 'bubble', text: 'I can fetch your reports, explain charges, or raise a ticket. What do you need?' }], state: 'greeting' };
  }
}

function resolveMessageIntent(msg: string): string {
  const m = msg.toLowerCase();
  if (/no ?data|nodata|no p&?l|trigger error/.test(m)) return 'trigger_error';
  if (/p&?l|pnl|profit/.test(m)) return 'report_pnl';
  if (/contract ?note/.test(m)) return 'report_contract_notes';
  if (/brokerage|charge/.test(m)) return 'report_brokerage';
  if (/holding/.test(m)) return 'report_holding';
  if (/ticket|escalat/.test(m)) return 'raise_ticket';
  if (/ledger/.test(m)) return 'report_pnl'; // ledger reuses the stepper shape in the mock
  return 'rag_qa';
}

function handleAction(st: ThreadState, threadId: string, turn: number, action: ChipAction, echoFallback: string): ChatResponse {
  const payload = (action.payload ?? {}) as Record<string, string>;
  switch (action.kind) {
    case 'send_text': {
      const intent = payload.intent ?? resolveMessageIntent(payload.text ?? echoFallback);
      const { blocks, state } = intentBlocks(intent, payload.text ?? echoFallback);
      return response(threadId, turn, blocks, state, st);
    }
    case 'select_param':
      return advancePnl(st, threadId, turn, payload);
    case 'open_calendar':
      return response(threadId, turn, [{ type: 'bubble', text: 'Pick your dates.' }, fx.calendar], 'collecting', st);
    case 'raise_ticket':
      return response(threadId, turn, [fx.ticketConfirmation], 'escalated', st);
    case 'call_support':
      return response(threadId, turn, [{ type: 'bubble', text: 'Call Choice support at 1800-XXXXXXX, 9am–6pm IST.' }], 'delivered', st);
    case 'email':
      return response(threadId, turn, [{ type: 'bubble', text: 'Sent to your registered email san***.harsha@gmail.com.' }], 'delivered', st);
    case 'retry':
      return response(threadId, turn, [{ type: 'bubble', text: 'Trying that again…' }], 'collecting', st);
    case 'deep_link':
      return response(threadId, turn, [{ type: 'bubble', text: 'Opening that for you…' }], 'delivered', st);
    case 'show_more':
    default:
      return response(threadId, turn, intentBlocks('default', echoFallback).blocks, 'greeting', st);
  }
}

/** The mock turn handler. Deterministic; state keyed by thread_id. */
export function handleChat(req: ChatRequest): ChatResponse {
  const clientId = req.session?.user_id || 'X008593';
  const isFirst = !req.thread_id;
  const threadId = req.thread_id ?? `mock-thread-${++threadSeq}`;

  let st = threads.get(threadId);
  if (!st) {
    st = { clientId, messagesUsed: 0, pnl: {} };
    threads.set(threadId, st);
  }

  if (isFirst) {
    // Session-seed turn: config_slice + greeting bubble + entry chips.
    const config = buildConfigSlice(req.session.entry_surface, clientId);
    const blocks: Block[] = [
      { type: 'bubble', text: config.greeting },
      { type: 'chip_row', chips: config.entry_chips },
    ];
    return response(threadId, 0, blocks, 'greeting', st, config);
  }

  st.messagesUsed += 1;
  const turn = (req.turn_number ?? 0);

  if (req.action) return handleAction(st, threadId, turn, req.action, req.message ?? '');
  if (req.message) {
    const intent = resolveMessageIntent(req.message);
    if (intent === 'trigger_error') {
      return response(threadId, turn, [{ type: 'user_bubble', text: req.message }, fx.errorBubble], 'error', st);
    }
    const { blocks, state } = intentBlocks(intent, req.message);
    return response(threadId, turn, blocks, state, st);
  }
  // Empty turn — echo greeting bubble only.
  return response(threadId, turn, [{ type: 'bubble', text: 'How can I help?' }], 'greeting', st);
}
