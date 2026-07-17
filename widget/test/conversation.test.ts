import { describe, it, expect, vi, afterEach } from 'vitest';
import { Conversation } from '../src/state/conversation';
import { ChatTransportError } from '../src/api/chatClient';
import type { ChatRequest, SessionContext, TypedChatResponse } from '../src/api/wireTypes';

const session: SessionContext = {
  user_id: 'X008593',
  session_id: 'sess-1',
  access_token: 'jwt-SECRET-XYZ',
  platform: 'web',
  page: 'support',
  entry_surface: 'support',
  is_dark_theme: false,
};

function reply(over: Partial<TypedChatResponse>): TypedChatResponse {
  return {
    thread_id: 'th-1',
    turn_number: 0,
    blocks: [],
    conversation_state: 'greeting',
    caps: { messages_used: 0, messages_cap: 10, follow_ups_used: 0 },
    ...over,
  };
}

type PC = (req: ChatRequest) => Promise<TypedChatResponse>;

afterEach(() => vi.restoreAllMocks());

describe('conversation turn loop', () => {
  it('seed sends turn 0 with no thread_id and captures config_slice', async () => {
    const post = vi.fn(async (_req: ChatRequest) =>
      reply({
        blocks: [{ type: 'bubble', text: 'hi' }, { type: 'chip_row', chips: [] }],
        config_slice: { greeting: 'hi', entry_chips: [], limits: { page_size: 10, note_threshold: 50, message_cap: 10, follow_up_cap: 2 } },
      }),
    );
    const c = new Conversation(session, { post });
    await c.seed();
    expect(post).toHaveBeenCalledTimes(1);
    const req = post.mock.calls[0][0] as ChatRequest;
    expect(req.thread_id).toBeUndefined();
    expect(req.turn_number).toBe(0);
    expect(req.session).toBe(session);
    const s = c.getSnapshot();
    expect(s.blocks.map((b) => b.type)).toEqual(['bubble', 'chip_row']);
    expect(s.config?.greeting).toBe('hi');
    expect(s.seeded).toBe(true);
  });

  it('issues exactly one POST per action and threads thread_id + turn_number', async () => {
    const post = vi
      .fn<PC>()
      .mockResolvedValueOnce(reply({ thread_id: 'th-1', turn_number: 0, blocks: [{ type: 'bubble', text: 'seed' }] }))
      .mockResolvedValueOnce(reply({ thread_id: 'th-1', turn_number: 1, blocks: [{ type: 'user_bubble', text: 'Get my P&L' }, { type: 'stepper_card', steps: [] }] }));
    const c = new Conversation(session, { post });
    await c.seed();
    await c.send('Get my P&L');
    expect(post).toHaveBeenCalledTimes(2);
    const second = post.mock.calls[1][0] as ChatRequest;
    expect(second.thread_id).toBe('th-1');
    expect(second.turn_number).toBe(1);
    expect(second.message).toBe('Get my P&L');
    // appended in order after the seed block
    expect(c.getSnapshot().blocks.map((b) => b.type)).toEqual(['bubble', 'user_bubble', 'stepper_card']);
  });

  it('never fires a second POST while one is in flight (single-flight)', async () => {
    let resolve!: (r: TypedChatResponse) => void;
    const post = vi.fn(() => new Promise<TypedChatResponse>((r) => (resolve = r)));
    const c = new Conversation(session, { post });
    const p1 = c.send('one');
    const p2 = c.send('two'); // ignored while pending
    resolve(reply({ blocks: [{ type: 'bubble', text: 'ok' }] }));
    await Promise.all([p1, p2]);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('transport failure appends a synthesized E-TIMEOUT error bubble', async () => {
    const post = vi.fn(async () => {
      throw new ChatTransportError('network');
    });
    const c = new Conversation(session, { post });
    await c.send('hello');
    const blocks = c.getSnapshot().blocks;
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ type: 'error_bubble', code: 'E-TIMEOUT' });
    expect(c.getSnapshot().state).toBe('error');
  });

  it('echoes access_token in the request body but never logs it', async () => {
    const logs: string[] = [];
    for (const m of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, m).mockImplementation((...a: unknown[]) => logs.push(a.map(String).join(' ')));
    }
    const post = vi.fn(async (_req: ChatRequest) => reply({ blocks: [{ type: 'bubble', text: 'ok' }] }));
    const c = new Conversation(session, { post });
    await c.send('hi');
    const req = post.mock.calls[0][0];
    expect(req.session.access_token).toBe('jwt-SECRET-XYZ'); // echoed to backend
    expect(logs.join('\n')).not.toContain('jwt-SECRET-XYZ'); // but never logged
  });

  it('marks the turn slow after the >5s threshold', async () => {
    vi.useFakeTimers();
    let resolve!: (r: TypedChatResponse) => void;
    const post = vi.fn(() => new Promise<TypedChatResponse>((r) => (resolve = r)));
    const c = new Conversation(session, { post, slowMs: 5000 });
    const p = c.send('slow one');
    expect(c.getSnapshot().slow).toBe(false);
    vi.advanceTimersByTime(5001);
    expect(c.getSnapshot().slow).toBe(true);
    resolve(reply({ blocks: [{ type: 'bubble', text: 'done' }] }));
    await p;
    expect(c.getSnapshot().slow).toBe(false);
    vi.useRealTimers();
  });
});

describe('chatClient over MSW', () => {
  it('seed reaches the mock and returns greeting + entry chips + config_slice', async () => {
    const { resetMock } = await import('../mock/server');
    resetMock();
    const c = new Conversation(session);
    await c.seed();
    const s = c.getSnapshot();
    expect(s.blocks[0]).toMatchObject({ type: 'bubble' });
    expect(s.blocks[1]).toMatchObject({ type: 'chip_row' });
    expect(s.config?.entry_chips.length).toBeGreaterThan(0);
    expect(s.threadId).toBeTruthy();
  });
});
