import { describe, it, expect, vi, afterEach } from 'vitest';
import { bootstrap, entrySurfaceFromPage } from '../src/bootstrap';

const FULL =
  '?userId=X008593&sessionId=sess-abc&accessToken=jwt-SECRET-123' +
  '&isDarkTheme=true&platform=webview&page=reports';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('bootstrap param parsing', () => {
  it('maps all six params into the SessionContext', () => {
    const { session } = bootstrap(FULL);
    expect(session).toMatchObject({
      user_id: 'X008593',
      session_id: 'sess-abc',
      access_token: 'jwt-SECRET-123',
      platform: 'webview',
      page: 'reports',
      entry_surface: 'reports',
      is_dark_theme: true,
    });
  });

  it('derives entry_surface from page (reports vs support)', () => {
    expect(entrySurfaceFromPage('reports')).toBe('reports');
    expect(entrySurfaceFromPage('report-screen')).toBe('reports');
    expect(entrySurfaceFromPage('support')).toBe('support');
    expect(entrySurfaceFromPage('help')).toBe('support');
    expect(bootstrap('?page=support').session.entry_surface).toBe('support');
  });

  it('defaults missing params (platform=web, page=support, entry=support)', () => {
    const { session, themeParam } = bootstrap('');
    expect(session.platform).toBe('web');
    expect(session.page).toBe('support');
    expect(session.entry_surface).toBe('support');
    expect(session.is_dark_theme).toBe(false);
    expect(themeParam).toBeNull();
  });

  it('themeParam preserves presence: absent → null, false → false, true → true', () => {
    expect(bootstrap('').themeParam).toBeNull();
    expect(bootstrap('?isDarkTheme=false').themeParam).toBe(false);
    expect(bootstrap('?isDarkTheme=true').themeParam).toBe(true);
  });
});

describe('access token safety', () => {
  it('never writes accessToken (or sessionId) to localStorage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    bootstrap(FULL);
    for (const call of setItem.mock.calls) {
      expect(call.join('|')).not.toContain('jwt-SECRET-123');
      expect(call.join('|')).not.toContain('sess-abc');
    }
    // Nothing persisted at all by bootstrap.
    expect(localStorage.length).toBe(0);
  });

  it('never logs accessToken to the console', () => {
    const logs: string[] = [];
    for (const m of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, m).mockImplementation((...a: unknown[]) => {
        logs.push(a.map(String).join(' '));
      });
    }
    bootstrap(FULL);
    expect(logs.join('\n')).not.toContain('jwt-SECRET-123');
  });
});
