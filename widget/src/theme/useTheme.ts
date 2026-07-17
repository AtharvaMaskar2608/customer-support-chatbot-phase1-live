import { useEffect } from 'react';

/**
 * Resolve the widget theme from the `isDarkTheme` URL param, falling back to
 * the OS `prefers-color-scheme` when the param was absent.
 *
 * @param themeParam
 *   `true`  → force dark  (sets `data-theme="dark"`)
 *   `false` → force light (sets `data-theme="light"`)
 *   `null`  → param absent → remove `data-theme` and let the CSS media query
 *             (`prefers-color-scheme`) decide.
 *
 * Theming is CSS-variable driven (see tokens.css). No web font is ever loaded.
 */
export function applyTheme(themeParam: boolean | null, root: HTMLElement = document.documentElement): void {
  if (themeParam === null) {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', themeParam ? 'dark' : 'light');
  }
}

export function useTheme(themeParam: boolean | null): void {
  useEffect(() => {
    applyTheme(themeParam);
  }, [themeParam]);
}
