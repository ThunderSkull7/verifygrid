import React, { useEffect, useRef, useState } from 'react';
import { Check, Monitor, Moon, Palette, Sun } from 'lucide-react';
import { useTheme } from '../context/useTheme';
import type { AccentColorKey, ThemeMode } from '../context/themeContextDef';

interface AppearanceControlProps {
  /** 'sidebar' renders a full-width labelled button, 'compact' an icon-only button. */
  variant?: 'sidebar' | 'compact';
}

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

const ACCENT_OPTIONS: { value: AccentColorKey; label: string; color: string }[] = [
  { value: 'green', label: 'Green', color: '#10b981' },
  { value: 'blue', label: 'Blue', color: '#3b82f6' },
  { value: 'indigo', label: 'Indigo', color: '#6366f1' },
  { value: 'purple', label: 'Purple', color: '#a855f7' },
  { value: 'teal', label: 'Teal', color: '#14b8a6' },
  { value: 'cyan', label: 'Cyan', color: '#06b6d4' },
  { value: 'orange', label: 'Orange', color: '#f97316' },
  { value: 'rose', label: 'Rose', color: '#f43f5e' },
  { value: 'neutral', label: 'Slate', color: '#64748b' },
];

export const AppearanceControl: React.FC<AppearanceControlProps> = ({ variant = 'sidebar' }) => {
  const { theme, resolvedTheme, accent, setTheme, setAccent } = useTheme();
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

  const themeLabel = THEME_OPTIONS.find((o) => o.value === theme)?.label ?? 'System';
  const accentLabel = ACCENT_OPTIONS.find((o) => o.value === accent)?.label ?? 'Green';

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
          <span className="appearance-btn-value">
            {accentLabel} · {themeLabel}
          </span>
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
          {resolvedTheme === 'dark' ? <Moon size={17} /> : <Sun size={17} />}
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

            <div className="appearance-section">
              <span className="appearance-label" id="vg-accent-label">
                Accent colour
              </span>
              <div className="accent-grid" role="radiogroup" aria-labelledby="vg-accent-label">
                {ACCENT_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={accent === option.value}
                    aria-label={option.label}
                    title={option.label}
                    className={`accent-swatch ${accent === option.value ? 'selected' : ''}`}
                    style={{ '--swatch': option.color } as React.CSSProperties}
                    onClick={() => setAccent(option.value)}
                  />
                ))}
              </div>
            </div>

            <div className="appearance-current-note">
              <Check size={13} />
              <span>
                {accentLabel} accent · {resolvedTheme === 'dark' ? 'Dark' : 'Light'} theme active
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
