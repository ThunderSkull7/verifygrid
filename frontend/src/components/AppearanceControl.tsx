import React, { useEffect, useRef, useState } from 'react';
import { Check, Moon, Palette, Sun } from 'lucide-react';
import { useTheme } from '../context/useTheme';
import type { ThemeMode } from '../context/themeContextDef';

interface AppearanceControlProps {
  /** 'sidebar' renders a full-width labelled button, 'compact' an icon-only button. */
  variant?: 'sidebar' | 'compact';
}

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
];

export const AppearanceControl: React.FC<AppearanceControlProps> = ({ variant = 'sidebar' }) => {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  const themeLabel = THEME_OPTIONS.find((o) => o.value === theme)?.label ?? 'Light';

  return (
    <div className="appearance-wrap" ref={wrapRef}>
      {variant === 'sidebar' ? (
        <button
          type="button"
          className="appearance-btn"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label="Appearance settings"
        >
          <Palette size={16} />
          <span className="appearance-btn-label">Appearance</span>
          <span className="appearance-btn-value">{themeLabel}</span>
        </button>
      ) : (
        <button
          type="button"
          className="icon-btn subtle"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label="Appearance settings"
          title="Appearance settings"
        >
          {theme === 'dark' ? <Moon size={17} /> : <Sun size={17} />}
        </button>
      )}

      {open && (
        <>
          <div className="appearance-overlay" onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            className={`appearance-panel ${variant === 'sidebar' ? 'up' : 'down'}`}
            role="dialog"
            aria-label="Appearance settings"
          >
            <div className="appearance-section">
              <span className="appearance-label" id="vg-theme-label">
                Theme
              </span>
              <div className="segmented" role="radiogroup" aria-labelledby="vg-theme-label">
                {THEME_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={theme === option.value}
                    className={`segmented-btn ${theme === option.value ? 'active' : ''}`}
                    onClick={() => setTheme(option.value)}
                  >
                    <option.icon size={14} />
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="appearance-current-note">
              <Check size={13} />
              <span>{themeLabel} theme active</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
