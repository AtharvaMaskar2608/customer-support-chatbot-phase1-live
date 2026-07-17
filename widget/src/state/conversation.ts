import { useSyncExternalStore, useMemo } from 'react';
import type {
  Block,
  Caps,
  ChatRequest,
  ChipAction,
  ConfigSlice,
  ConversationState as WireConversationState,
  SessionContext,
} from '../api/wireTypes';
import { postChat, TRANSPORT_ERROR_BLOCK, type PostChat } from '../api/chatClient';

/** UI-facing conversation snapshot. `blocks` is an append-only log. */
export interface ConversationSnapshot {
  blocks: Block[];
  threadId?: string;
  turnNumber: number;
  caps?: Caps;
  state: WireConversationState;
  config?: ConfigSlice;
  pending: boolean;
  /** True once an in-flight turn passes the slow threshold (spec §8.2, >5s). */
  slow: boolean;
  seeded: boolean;
}

export interface ConversationDeps {
  post?: PostChat;
  slowMs?: number;
  setTimer?: typeof setTimeout;
  clearTimer?: typeof clearTimeout;
}

const EMPTY: ConversationSnapshot = {
  blocks: [],
  turnNumber: 0,
  state: 'greeting',
  pending: false,
  slow: false,
  seeded: false,
};

/**
 * Framework-agnostic conversation controller. Owns the append-only block log
 * and the turn loop: exactly one POST /api/chat per user action, blocks
 * appended in the order the server returns them, thread_id/turn_number
 * threaded, caps surfaced. Transport failure appends a synthesized E-TIMEOUT
 * error bubble (never a raw HTTP code). The widget never synthesizes any other
 * block or reorders the server's blocks.
 */
export class Conversation {
  private snap: ConversationSnapshot = EMPTY;
  private listeners = new Set<() => void>();
  private requestTurn = 0;
  private readonly post: PostChat;
  private readonly slowMs: number;
  private readonly setTimer: typeof setTimeout;
  private readonly clearTimer: typeof clearTimeout;

  constructor(
    private readonly session: SessionContext,
    deps: ConversationDeps = {},
  ) {
    this.post = deps.post ?? postChat;
    this.slowMs = deps.slowMs ?? 5000;
    this.setTimer = deps.setTimer ?? setTimeout;
    this.clearTimer = deps.clearTimer ?? clearTimeout;
  }

  getSnapshot = (): ConversationSnapshot => this.snap;

  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  };

  private set(patch: Partial<ConversationSnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    this.listeners.forEach((l) => l());
  }

  /** First turn: no thread_id, turn_number 0. Seeds config + entry surface. */
  seed(): Promise<void> {
    if (this.snap.seeded || this.snap.pending) return Promise.resolve();
    return this.turn({});
  }

  /** "Start over" — drop the block log + thread and re-seed a fresh session. */
  reset(): Promise<void> {
    this.snap = EMPTY;
    this.requestTurn = 0;
    this.listeners.forEach((l) => l());
    return this.seed();
  }

  send(text: string): Promise<void> {
    return this.turn({ message: text });
  }

  act(action: ChipAction): Promise<void> {
    return this.turn({ action });
  }

  private async turn(payload: { message?: string; action?: ChipAction }): Promise<void> {
    if (this.snap.pending) return; // single-flight: exactly one POST per action
    const req: ChatRequest = {
      session: this.session,
      turn_number: this.requestTurn,
      ...(this.snap.threadId ? { thread_id: this.snap.threadId } : {}),
      ...(payload.message !== undefined ? { message: payload.message } : {}),
      ...(payload.action !== undefined ? { action: payload.action } : {}),
    };

    this.set({ pending: true, slow: false });
    const slowTimer = this.setTimer(() => this.set({ slow: true }), this.slowMs);

    try {
      const res = await this.post(req);
      this.requestTurn = res.turn_number + 1;
      this.set({
        blocks: [...this.snap.blocks, ...res.blocks],
        threadId: res.thread_id,
        turnNumber: res.turn_number,
        caps: res.caps,
        state: res.conversation_state,
        config: res.config_slice ?? this.snap.config,
        seeded: true,
      });
    } catch {
      // Transport failure → synthesized E-TIMEOUT bubble; log stays append-only.
      this.requestTurn += 1;
      this.set({
        blocks: [...this.snap.blocks, TRANSPORT_ERROR_BLOCK],
        state: 'error',
        seeded: true,
      });
    } finally {
      this.clearTimer(slowTimer);
      this.set({ pending: false, slow: false });
    }
  }
}

/** React binding. Returns the live snapshot; identity stable across renders. */
export function useConversation(conversation: Conversation): ConversationSnapshot {
  return useSyncExternalStore(conversation.subscribe, conversation.getSnapshot, conversation.getSnapshot);
}

/** Create a Conversation memoized on session identity. */
export function useNewConversation(session: SessionContext, deps?: ConversationDeps): Conversation {
  return useMemo(() => new Conversation(session, deps), [session]); // eslint-disable-line react-hooks/exhaustive-deps
}
