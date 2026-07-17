import type { Plugin } from 'vite';
import { handleChat } from './server';
import type { ChatRequest } from '../src/api/wireTypes';

// In-process POST /api/chat middleware for `vite --mode mock`. Same core
// (handleChat) the vitest MSW suite uses, so dev/E2E and tests never diverge.
export function mockApiPlugin(): Plugin {
  return {
    name: 'jini-mock-api',
    configureServer(server) {
      server.middlewares.use('/api/chat', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          let parsed: ChatRequest;
          try {
            parsed = JSON.parse(body || '{}') as ChatRequest;
          } catch {
            res.statusCode = 400;
            res.end('{"error":"bad json"}');
            return;
          }
          const out = handleChat(parsed);
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(out));
        });
      });
    },
  };
}
