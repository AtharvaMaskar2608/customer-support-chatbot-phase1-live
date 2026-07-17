// Mock implementation of the POST /api/chat wire contract. This is the SINGLE
// source of mock truth: the vitest suite drives it through MSW, and the Vite
// `mock` mode drives it through an in-process middleware. Fleshed out in T5.
import type { ChatRequest, ChatResponse } from '../src/api/wireTypes';

export function handleChat(_req: ChatRequest): ChatResponse {
  // Placeholder — replaced in T5 with fixture-driven flow routing.
  return {
    thread_id: 'mock-thread',
    turn_number: 0,
    blocks: [],
    conversation_state: 'greeting',
    caps: { messages_used: 0, messages_cap: 10, follow_ups_used: 0 },
  };
}
