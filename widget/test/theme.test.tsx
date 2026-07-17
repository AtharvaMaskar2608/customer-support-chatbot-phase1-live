import { describe, it, expect, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { applyTheme, useTheme } from '../src/theme/useTheme';

function Themed({ param }: { param: boolean | null }) {
  useTheme(param);
  return null;
}

afterEach(() => {
  document.documentElement.removeAttribute('data-theme');
});

describe('theme resolution', () => {
  it('isDarkTheme=true forces data-theme="dark"', () => {
    render(<Themed param={true} />);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('isDarkTheme=false forces data-theme="light"', () => {
    render(<Themed param={false} />);
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('param absent (null) removes data-theme so prefers-color-scheme decides', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    applyTheme(null);
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });
});

// Walk every source file under widget/src + tokens to prove no web font is
// loaded (spec §8.1: system font stack only).
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe('no web font (spec §8.1)', () => {
  it('never references @font-face, a font CDN, or a font <link>', () => {
    const root = join(__dirname, '..', 'src');
    const offenders: string[] = [];
    for (const file of walk(root)) {
      if (!/\.(css|ts|tsx|html)$/.test(file)) continue;
      const text = readFileSync(file, 'utf8');
      if (/@font-face|fonts\.googleapis|fonts\.gstatic|typekit|rel=["']?stylesheet["']?[^>]*font/i.test(text)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
