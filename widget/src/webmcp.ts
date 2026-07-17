/// <reference types="webmcp-types" />
// webmcp-types is a TYPES-ONLY package (no runtime entry): it augments
// `Document` with the optional `modelContext`. Referenced, never imported at
// runtime — the widget adds no WebMCP runtime dependency and no polyfill.
import type { Block, Chip, ChipAction, Caps, ConversationState } from './api/wireTypes';

/**
 * WebMCP page-tool registration (W3C WebMCP draft — agent-native surface).
 *
 * Registers a small set of page-level tools via `document.modelContext`. It is
 * feature-detected: on any browser that does not implement the draft it is a
 * silent no-op — no polyfill, no runtime dependency, no behavioral change for
 * normal users. The tools call the SAME internal actions the UI uses (send a
 * turn, tap a chip, read state); they add no new network or contract surface.
 */

/** Read-only view of the current turn the agent can inspect. */
export interface WebMcpState {
  blocks: Array<{ type: Block['type']; text?: string }>;
  chips: Array<{ label: string }>;
  state: ConversationState;
  turn_number: number;
  caps?: Caps;
  pending: boolean;
}

/** Bridge into the live Conversation — the widget's own dispatch, nothing new. */
export interface WebMcpBridge {
  sendMessage(text: string): void;
  tapChip(action: ChipAction): void;
  getState(): WebMcpState;
  /** The chips currently actionable, in display order (for tap_chip lookup). */
  actionableChips(): Chip[];
}

/** Collect every chip the user could currently tap, across all block kinds. */
export function actionableChips(blocks: Block[]): Chip[] {
  const chips: Chip[] = [];
  for (const b of blocks) {
    switch (b.type) {
      case 'chip_row':
        chips.push(...b.chips);
        break;
      case 'stepper_card':
        for (const step of b.steps) if (step.state === 'active' && step.chips) chips.push(...step.chips);
        break;
      case 'error_bubble':
        if (b.chips) chips.push(...b.chips);
        break;
      case 'ticket_confirmation':
        if (b.chips) chips.push(...b.chips);
        break;
      case 'note_list_card':
        if (b.footer_chips) chips.push(...b.footer_chips);
        break;
      case 'file_card':
        if (b.actions) chips.push(...b.actions);
        break;
      default:
        break;
    }
  }
  return chips;
}

const SEND_MESSAGE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: { text: { type: 'string', description: 'The free-text message to send.' } },
  required: ['text'],
} as const;

const TAP_CHIP_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: { label: { type: 'string', description: 'The exact label of a currently-visible chip.' } },
  required: ['label'],
} as const;

const GET_STATE_SCHEMA = { type: 'object', additionalProperties: false, properties: {} } as const;

/**
 * Register the page tools if WebMCP is available. Returns a cleanup function
 * that unregisters them; a no-op cleanup when WebMCP is absent.
 */
export function registerPageTools(bridge: WebMcpBridge, doc: Document = document): () => void {
  const mc = doc.modelContext;
  if (!mc) return () => {}; // feature-detected no-op

  const controller = new AbortController();
  const opts = { signal: controller.signal };

  void mc.registerTool(
    {
      name: 'send_message',
      description: 'Send a free-text message to the Choice Jini chat, as if the user typed it.',
      inputSchema: SEND_MESSAGE_SCHEMA,
      execute: (input: Record<string, unknown>) => {
        const text = String((input as { text?: unknown }).text ?? '').trim();
        if (!text) return { ok: false, error: 'text is required' };
        bridge.sendMessage(text);
        return { ok: true };
      },
    },
    opts,
  );

  void mc.registerTool(
    {
      name: 'tap_chip',
      description: 'Tap one of the currently-visible quick-reply chips by its exact label.',
      inputSchema: TAP_CHIP_SCHEMA,
      execute: (input: Record<string, unknown>) => {
        const label = String((input as { label?: unknown }).label ?? '');
        const chip = bridge.actionableChips().find((c) => c.label === label);
        if (!chip) return { ok: false, error: `no visible chip labelled "${label}"` };
        bridge.tapChip(chip.action);
        return { ok: true };
      },
    },
    opts,
  );

  void mc.registerTool(
    {
      name: 'get_conversation_state',
      description: 'Read the current Choice Jini conversation: rendered blocks, visible chips, turn state, and caps.',
      inputSchema: GET_STATE_SCHEMA,
      annotations: { readOnlyHint: true },
      execute: () => bridge.getState(),
    },
    opts,
  );

  return () => controller.abort();
}
