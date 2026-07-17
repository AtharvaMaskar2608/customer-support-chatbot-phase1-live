import type { SessionContext, EntrySurface } from './api/wireTypes';

/**
 * The result of parsing the app-handoff URL query params once at mount.
 *
 * `session` is the typed context echoed on every POST /api/chat. `themeParam`
 * preserves whether `isDarkTheme` was present in the URL (true/false) or absent
 * (null → fall back to prefers-color-scheme); this distinction is lost in
 * `session.is_dark_theme`, which the contract requires as a plain boolean.
 *
 * SECURITY: `access_token` and `session_id` are held in memory only. They are
 * NEVER written to localStorage/sessionStorage, never logged, never rendered.
 */
export interface Bootstrap {
  session: SessionContext;
  themeParam: boolean | null;
}

/** `page` selects the entry seed: a reports-screen handoff → 1b, else 1a. */
export function entrySurfaceFromPage(page: string): EntrySurface {
  return /report/i.test(page) ? 'reports' : 'support';
}

function parseBool(raw: string | null): boolean | null {
  if (raw === null) return null;
  if (raw === 'true' || raw === '1') return true;
  if (raw === 'false' || raw === '0') return false;
  return null;
}

/**
 * Parse the six handoff params into a SessionContext. Called once at mount; the
 * result is held in memory for the life of the session.
 */
export function bootstrap(search: string = window.location.search): Bootstrap {
  const q = new URLSearchParams(search);
  const page = q.get('page') ?? 'support';
  const themeParam = parseBool(q.get('isDarkTheme'));

  const session: SessionContext = {
    user_id: q.get('userId') ?? '',
    session_id: q.get('sessionId') ?? '',
    access_token: q.get('accessToken') ?? '',
    platform: q.get('platform') ?? 'web',
    page,
    entry_surface: entrySurfaceFromPage(page),
    is_dark_theme: themeParam ?? false,
  };

  return { session, themeParam };
}
