import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { handleChat } from '../mock/server';
import type { ChatRequest } from '../src/api/wireTypes';

// MSW handlers wrapping the SAME handleChat the Vite mock middleware uses, so
// the vitest suite exercises the real mock flow logic over fetch.
export const handlers = [
  http.post('*/api/chat', async ({ request }) => {
    const body = (await request.json()) as ChatRequest;
    return HttpResponse.json(handleChat(body));
  }),
];

export const mswServer = setupServer(...handlers);
