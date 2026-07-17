import '@testing-library/jest-dom/vitest';
import { afterEach, afterAll, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import { mswServer } from './msw';
import { resetMock } from '../mock/server';

// jsdom ships no PointerEvent, so fireEvent.pointer* drops clientX/clientY and
// pointer-drag handlers never see coordinates. Shim it with a MouseEvent
// subclass (which does carry clientX/clientY) so drag/swipe can be tested.
if (typeof (globalThis as { PointerEvent?: unknown }).PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
      this.pointerId = params.pointerId ?? 1;
    }
  }
  (globalThis as { PointerEvent?: unknown }).PointerEvent = PointerEventPolyfill;
}
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};

beforeAll(() => mswServer.listen({ onUnhandledRequest: 'bypass' }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  mswServer.resetHandlers();
  resetMock();
});

afterAll(() => mswServer.close());
