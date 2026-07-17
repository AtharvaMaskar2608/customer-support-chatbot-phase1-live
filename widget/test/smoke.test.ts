import { describe, it, expect } from 'vitest';

// Scaffold smoke test — proves the vitest + jsdom harness runs. Replaced by
// real behavior tests as tasks land.
describe('scaffold', () => {
  it('runs in a jsdom environment', () => {
    expect(typeof document).toBe('object');
    expect(document.createElement('div')).toBeInstanceOf(HTMLElement);
  });
});
