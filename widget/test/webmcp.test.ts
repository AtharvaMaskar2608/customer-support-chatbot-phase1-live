import { describe, it, expect, vi } from 'vitest';
import { registerPageTools, actionableChips, type WebMcpBridge, type WebMcpState } from '../src/webmcp';
import type { Block, Chip, ChipAction } from '../src/api/wireTypes';

interface FakeTool {
  name: string;
  description: string;
  inputSchema?: object;
  annotations?: { readOnlyHint?: boolean };
  execute: (input: Record<string, unknown>) => unknown;
}

function fakeDoc() {
  const registered: FakeTool[] = [];
  const modelContext = {
    registerTool: vi.fn(async (tool: FakeTool) => {
      registered.push(tool);
    }),
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return true;
    },
    ontoolchange: null,
  };
  return { doc: { modelContext } as unknown as Document, registered, registerSpy: modelContext.registerTool };
}

function makeBridge(over: Partial<WebMcpBridge> = {}): WebMcpBridge {
  const state: WebMcpState = { blocks: [], chips: [], state: 'greeting', turn_number: 0, pending: false };
  return {
    sendMessage: vi.fn(),
    tapChip: vi.fn(),
    getState: () => state,
    actionableChips: () => [],
    ...over,
  };
}

describe('WebMCP registration', () => {
  it('registers exactly the three page tools with valid input schemas', async () => {
    const { doc, registered } = fakeDoc();
    registerPageTools(makeBridge(), doc);
    const names = registered.map((t) => t.name).sort();
    expect(names).toEqual(['get_conversation_state', 'send_message', 'tap_chip']);
    for (const t of registered) {
      expect(t.description.length).toBeGreaterThan(0);
      expect(t.inputSchema).toMatchObject({ type: 'object' });
    }
    expect(registered.find((t) => t.name === 'get_conversation_state')!.annotations).toMatchObject({ readOnlyHint: true });
  });

  it('send_message routes to the same send the UI uses', () => {
    const { doc, registered } = fakeDoc();
    const bridge = makeBridge();
    registerPageTools(bridge, doc);
    const tool = registered.find((t) => t.name === 'send_message')!;
    const res = tool.execute({ text: '  hello  ' }) as { ok: boolean };
    expect(res.ok).toBe(true);
    expect(bridge.sendMessage).toHaveBeenCalledWith('hello');
  });

  it('tap_chip resolves the label to the chip action and dispatches it', () => {
    const { doc, registered } = fakeDoc();
    const action: ChipAction = { kind: 'send_text', payload: { intent: 'report_pnl' } };
    const chips: Chip[] = [{ label: '📊 Get my P&L', action }];
    const bridge = makeBridge({ actionableChips: () => chips });
    registerPageTools(bridge, doc);
    const tool = registered.find((t) => t.name === 'tap_chip')!;
    const res = tool.execute({ label: '📊 Get my P&L' }) as { ok: boolean };
    expect(res.ok).toBe(true);
    expect(bridge.tapChip).toHaveBeenCalledWith(action);
  });

  it('tap_chip returns an error for an unknown label', () => {
    const { doc, registered } = fakeDoc();
    const bridge = makeBridge({ actionableChips: () => [] });
    registerPageTools(bridge, doc);
    const tool = registered.find((t) => t.name === 'tap_chip')!;
    const res = tool.execute({ label: 'nope' }) as { ok: boolean };
    expect(res.ok).toBe(false);
    expect(bridge.tapChip).not.toHaveBeenCalled();
  });

  it('get_conversation_state returns the read-only snapshot', () => {
    const { doc, registered } = fakeDoc();
    const snap: WebMcpState = { blocks: [{ type: 'bubble', text: 'hi' }], chips: [{ label: 'x' }], state: 'collecting', turn_number: 2, pending: false };
    const bridge = makeBridge({ getState: () => snap });
    registerPageTools(bridge, doc);
    const tool = registered.find((t) => t.name === 'get_conversation_state')!;
    expect(tool.execute({})).toEqual(snap);
  });

  it('is a silent no-op when document.modelContext is absent', () => {
    const doc = {} as Document; // no modelContext
    const bridge = makeBridge();
    expect(() => registerPageTools(bridge, doc)()).not.toThrow();
    expect(bridge.sendMessage).not.toHaveBeenCalled();
  });
});

describe('actionableChips', () => {
  it('collects chips from chip rows, active stepper steps, errors, tickets, notes, and file actions', () => {
    const a = (kind: ChipAction['kind']): ChipAction => ({ kind, payload: {} });
    const blocks: Block[] = [
      { type: 'chip_row', chips: [{ label: 'row-chip', action: a('send_text') }] },
      {
        type: 'stepper_card',
        steps: [
          { id: 's1', title: '1', state: 'done', selected_label: 'x' },
          { id: 's2', title: '2', state: 'active', chips: [{ label: 'step-chip', action: a('select_param') }] },
        ],
      },
      { type: 'error_bubble', code: 'E-NODATA', text: 'e', chips: [{ label: 'err-chip', action: a('retry') }] },
      { type: 'file_card', filename: 'f', size_label: '1 KB', format: 'pdf', actions: [{ label: 'Download', action: a('deep_link') }] },
    ];
    const labels = actionableChips(blocks).map((c) => c.label);
    expect(labels).toEqual(['row-chip', 'step-chip', 'err-chip', 'Download']);
  });
});
