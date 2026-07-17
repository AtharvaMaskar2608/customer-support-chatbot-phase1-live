import type { ChatRequest, TypedChatResponse, ErrorBubbleBlock } from './wireTypes';

// The widget's ONLY network surface: POST /api/chat. Remote-config is folded
// into the first response's config_slice (frozen contract), so there is no
// second endpoint. No FinX/Freshdesk/byte-fetch/report-URL call ever lives here.

export const CHAT_ENDPOINT = '/api/chat';

/**
 * Client-synthesized error for a transport/HTTP failure. Domain errors arrive
 * as `error_bubble` blocks in a 200 body; only transport failures are
 * synthesized here. Copy is friendly + fixed — the widget NEVER surfaces raw
 * HTTP codes, Reason strings, or URLs (spec §2.6).
 */
export const TRANSPORT_ERROR_BLOCK: ErrorBubbleBlock = {
  type: 'error_bubble',
  code: 'E-TIMEOUT',
  text: 'I couldn’t reach the server just now. Want to try that again?',
  chips: [{ label: '↺ Retry', action: { kind: 'retry', payload: {} } }],
};

export class ChatTransportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChatTransportError';
  }
}

export type PostChat = (req: ChatRequest) => Promise<TypedChatResponse>;

/** POST one turn. Throws {@link ChatTransportError} on network/HTTP failure. */
export const postChat: PostChat = async (req) => {
  let res: Response;
  try {
    res = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(req),
    });
  } catch {
    // Never include the underlying error text — it may carry URLs/host detail.
    throw new ChatTransportError('network');
  }
  if (!res.ok) {
    throw new ChatTransportError(`http ${res.status}`);
  }
  return (await res.json()) as TypedChatResponse;
};
