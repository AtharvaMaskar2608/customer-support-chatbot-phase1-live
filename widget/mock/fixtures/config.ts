// Entry-seed config, delivered as `config_slice` in the FIRST /api/chat
// response only (the frozen contract folds remote-config into the seed turn, so
// the widget keeps a single network surface). Greeting/chips/limits/whats_new
// are server-supplied here — the widget never hardcodes them.
import type { ConfigSlice, Chip, ClientLimits, WhatsNewItem, EntrySurface } from '../../src/api/wireTypes';

export const LIMITS: ClientLimits = {
  page_size: 10,
  note_threshold: 50,
  message_cap: 10,
  follow_up_cap: 2,
};

const WHATS_NEW: WhatsNewItem[] = [
  { icon: '⚡', title: '11 reports, instant', body: 'P&L, Ledger, Holding, Tax Report + 7 more, delivered in chat as PDF or Excel.' },
  { icon: '🔓', title: 'No email verification', body: 'You’re logged in, so your reports come straight to you.' },
  { icon: '🎫', title: 'Tickets', body: 'Raise a support ticket without leaving chat.' },
];

const supportChips = (): Chip[] => [
  { label: '📊 Get my P&L', action: { kind: 'send_text', payload: { text: 'Get my P&L', intent: 'report_pnl' } } },
  { label: '📒 Show my ledger', action: { kind: 'send_text', payload: { text: 'Show my ledger', intent: 'report_ledger' } } },
  { label: '🧾 “How do I check my trade details?”', action: { kind: 'send_text', payload: { text: 'How do I check my trade details?', intent: 'rag_qa' } } },
  { label: '❓ What are my brokerage charges?', action: { kind: 'send_text', payload: { text: 'What are my brokerage charges?', intent: 'report_brokerage' } } },
];

const reportsChips = (): Chip[] => [
  { label: '📊 P&L Statement', action: { kind: 'send_text', payload: { text: 'P&L Statement', intent: 'report_pnl' } } },
  { label: '📒 Ledger', action: { kind: 'send_text', payload: { text: 'Ledger', intent: 'report_ledger' } } },
  { label: '📁 Holding Statement', action: { kind: 'send_text', payload: { text: 'Holding Statement', intent: 'report_holding' } } },
  { label: '🧾 Tax Report', action: { kind: 'send_text', payload: { text: 'Tax Report', intent: 'report_tax' } } },
];

/** Time-aware support greeting pool (spec: opening line rotates by clock). */
export function supportGreeting(clientId: string, hour: number = new Date().getHours()): string {
  if (hour >= 6 && hour < 9) return `Good morning, ${clientId} ☀️ What can I get for you?`;
  if (hour >= 9 && hour < 16) return `Hi ${clientId} — markets are live. Need a report or a quick answer?`;
  if (hour >= 16 && hour < 23) return `Hi ${clientId} 👋 Markets are closed — I’m not.`;
  return `Hey ${clientId} — what do you need? I can fetch your reports instantly, explain charges and processes, or check your ticket status. Files land right here in chat — no email verification needed.`;
}

export function reportsGreeting(clientId: string): string {
  return `Which report do you need, ${clientId}? Pick one below or just type — I’ll deliver it here as PDF or Excel.`;
}

export function buildConfigSlice(surface: EntrySurface, clientId: string, hour?: number): ConfigSlice {
  if (surface === 'reports') {
    return { greeting: reportsGreeting(clientId), entry_chips: reportsChips(), limits: LIMITS, whats_new: WHATS_NEW };
  }
  return { greeting: supportGreeting(clientId, hour), entry_chips: supportChips(), limits: LIMITS, whats_new: WHATS_NEW };
}

/** Reports 1b rotating input placeholder pool (long-tail sub-types 5–11). */
export const REPORTS_PLACEHOLDERS = [
  'or type: CML, Contract Note, Capital Gain, Global…',
  'or type: MTF Ledger, Tax P&L, Brokerage…',
];
