import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  ThemeContext,
  VALID_THEMES,
} from './themeContextDef';
import type { ThemeMode } from './themeContextDef';

const systemPrefersDark = (): boolean => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
};

/**
 * Restore a saved Light/Dark preference. A missing value, the retired
 * "system" value, or any unexpected value resolves once from the OS preference
 * so the first paint keeps the previous default appearance without exposing a
 * third mode.
 */
const readStoredTheme = (): ThemeMode => {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw && (VALID_THEMES as string[]).includes(raw)) {
      return raw as ThemeMode;
    }
  } catch {
    // Storage unavailable (private mode / sandbox) — fall back to the OS-resolved default.
  }
  return systemPrefersDark() ? 'dark' : DEFAULT_THEME;
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(readStoredTheme);

  // Apply the selected theme to the document root.
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === 'dark' ? '#0b1120' : '#f6f8fb');
    }
  }, [theme]);

  const setTheme = useCallback((next: ThemeMode) => {
    if (!(VALID_THEMES as string[]).includes(next)) return;
    setThemeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Ignore storage failures; the in-memory preference still applies.
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};
