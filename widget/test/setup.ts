import '@testing-library/jest-dom/vitest';
import { afterEach, afterAll, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import { mswServer } from './msw';
import { resetMock } from '../mock/server';

beforeAll(() => mswServer.listen({ onUnhandledRequest: 'bypass' }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  mswServer.resetHandlers();
  resetMock();
});

afterAll(() => mswServer.close());
