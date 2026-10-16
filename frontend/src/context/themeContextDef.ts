import { createContext } from 'react';

export type ThemeMode = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';
export type AccentColorKey =
  | 'green'
  | 'blue'
  | 'indigo'
  | 'purple'
  | 'teal'
  | 'cyan'
  | 'orange'
  | 'rose'
  | 'neutral';

export interface ThemeContextType {
  /** User preference: light, dark, or follow system. */
  theme: ThemeMode;
  /** Effective theme after resolving the system preference. */
  resolvedTheme: ResolvedTheme;
  /** Selected accent palette. */
  accent: AccentColorKey;
  setTheme: (theme: ThemeMode) => void;
  setAccent: (accent: AccentColorKey) => void;
}

export const THEME_STORAGE_KEY = 'verifygrid_theme';
export const ACCENT_STORAGE_KEY = 'verifygrid_accent';

export const DEFAULT_THEME: ThemeMode = 'system';
export const DEFAULT_ACCENT: AccentColorKey = 'green';

export const VALID_THEMES: ThemeMode[] = ['light', 'dark', 'system'];
export const VALID_ACCENTS: AccentColorKey[] = [
  'green',
  'blue',
  'indigo',
  'purple',
  'teal',
  'cyan',
  'orange',
  'rose',
  'neutral',
];

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
