import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ACCENT_STORAGE_KEY,
  DEFAULT_ACCENT,
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  ThemeContext,
  VALID_ACCENTS,
  VALID_THEMES,
} from './themeContextDef';
import type { AccentColorKey, ResolvedTheme, ThemeMode } from './themeContextDef';

const readStoredTheme = (): ThemeMode => {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw && (VALID_THEMES as string[]).includes(raw)) {
      return raw as ThemeMode;
    }
  } catch {
    // Storage unavailable (private mode / sandbox) — fall back to default.
  }
  return DEFAULT_THEME;
};

const readStoredAccent = (): AccentColorKey => {
  try {
    const raw = localStorage.getItem(ACCENT_STORAGE_KEY);
    if (raw && (VALID_ACCENTS as string[]).includes(raw)) {
      return raw as AccentColorKey;
    }
  } catch {
    // Storage unavailable — fall back to default.
  }
  return DEFAULT_ACCENT;
};

const systemPrefersDark = (): boolean => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(readStoredTheme);
  const [accent, setAccentState] = useState<AccentColorKey>(readStoredAccent);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);

  // Track the OS colour-scheme preference so "system" mode updates live.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const resolvedTheme: ResolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;

  // Apply theme attributes to the document root.
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', resolvedTheme);
    root.style.colorScheme = resolvedTheme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', resolvedTheme === 'dark' ? '#0b1120' : '#f6f8fb');
    }
  }, [resolvedTheme]);

  // Apply the accent palette attribute.
  useEffect(() => {
    document.documentElement.setAttribute('data-accent', accent);
  }, [accent]);

  const setTheme = useCallback((next: ThemeMode) => {
    if (!(VALID_THEMES as string[]).includes(next)) return;
    setThemeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Ignore storage failures; the in-memory preference still applies.
    }
  }, []);

  const setAccent = useCallback((next: AccentColorKey) => {
    if (!(VALID_ACCENTS as string[]).includes(next)) return;
    setAccentState(next);
    try {
      localStorage.setItem(ACCENT_STORAGE_KEY, next);
    } catch {
      // Ignore storage failures; the in-memory preference still applies.
    }
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, accent, setTheme, setAccent }),
    [theme, resolvedTheme, accent, setTheme, setAccent]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};
