import { createContext } from 'react';

export type ThemeMode = 'light' | 'dark';

export interface ThemeContextType {
  /** Selected appearance mode. */
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
}

export const THEME_STORAGE_KEY = 'verifygrid_theme';

export const DEFAULT_THEME: ThemeMode = 'light';

export const VALID_THEMES: ThemeMode[] = ['light', 'dark'];

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
