import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { UserEvent } from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppearanceControl } from '../../src/components/AppearanceControl';
import { Sidebar } from '../../src/components/Sidebar';
import { ThemeProvider } from '../../src/context/ThemeContext';
import { THEME_STORAGE_KEY } from '../../src/context/themeContextDef';

const authMocks = vi.hoisted(() => ({
  logout: vi.fn(),
}));

vi.mock('../../src/context/useAuth', () => ({
  useAuth: () => ({
    user: { full_name: 'Ada Lovelace', email: 'ada@example.com' },
    logout: authMocks.logout,
  }),
}));

const ACCENT_STORAGE_KEY = 'verifygrid_accent';

/** Make `prefers-color-scheme: dark` deterministic for the next render. */
function setPrefersDark(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function renderControl(variant: 'sidebar' | 'compact' = 'sidebar') {
  return render(
    <ThemeProvider>
      <AppearanceControl variant={variant} />
    </ThemeProvider>,
  );
}

async function openDialog(user: UserEvent) {
  await user.click(screen.getByRole('button', { name: 'Appearance settings' }));
  return screen.getByRole('dialog', { name: 'Appearance settings' });
}

const rootTheme = () => document.documentElement.getAttribute('data-theme');

const cssSource = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8');
const htmlSource = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

describe('Appearance control', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-accent');
    document.documentElement.style.colorScheme = '';
    document.documentElement.style.removeProperty('--primary-rgb');
    setPrefersDark(false);
  });

  it('selects Light mode from a saved Dark preference', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    const user = userEvent.setup();
    renderControl();

    expect(rootTheme()).toBe('dark');

    const dialog = await openDialog(user);
    const light = within(dialog).getByRole('radio', { name: 'Light' });
    const dark = within(dialog).getByRole('radio', { name: 'Dark' });
    expect(dark).toHaveAttribute('aria-checked', 'true');

    await user.click(light);

    expect(light).toHaveAttribute('aria-checked', 'true');
    expect(dark).toHaveAttribute('aria-checked', 'false');
    expect(rootTheme()).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('selects Dark mode from the default Light appearance', async () => {
    const user = userEvent.setup();
    renderControl();

    expect(rootTheme()).toBe('light');

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('radio', { name: 'Dark' }));

    expect(within(dialog).getByRole('radio', { name: 'Dark' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(rootTheme()).toBe('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('persists the selected appearance and restores it on the next mount', async () => {
    const user = userEvent.setup();
    const first = renderControl();

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('radio', { name: 'Dark' }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    first.unmount();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.style.colorScheme = '';

    renderControl();

    expect(rootTheme()).toBe('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    const reopened = await openDialog(user);
    expect(within(reopened).getByRole('radio', { name: 'Dark' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('uses the OS preference when no appearance has been saved', () => {
    setPrefersDark(false);
    const first = renderControl();
    expect(rootTheme()).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();

    first.unmount();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.style.colorScheme = '';
    setPrefersDark(true);
    renderControl();
    expect(rootTheme()).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('safely ignores an invalid stored appearance value', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    setPrefersDark(false);
    const user = userEvent.setup();
    renderControl();

    expect(rootTheme()).toBe('light');

    const dialog = await openDialog(user);
    expect(within(dialog).getByRole('radio', { name: 'Light' })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    await user.click(within(dialog).getByRole('radio', { name: 'Dark' }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('resolves the retired "system" value from the OS preference without a third mode', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'system');
    setPrefersDark(true);
    const user = userEvent.setup();
    renderControl();

    expect(rootTheme()).toBe('dark');

    const dialog = await openDialog(user);
    expect(within(dialog).queryAllByRole('radio')).toHaveLength(2);
    expect(within(dialog).queryByRole('radio', { name: /system/i })).toBeNull();
    expect(within(dialog).getByRole('radio', { name: 'Dark' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('ignores an obsolete accent value and never sets a palette attribute', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    localStorage.setItem(ACCENT_STORAGE_KEY, 'rose');
    renderControl();

    expect(rootTheme()).toBe('dark');
    expect(document.documentElement).not.toHaveAttribute('data-accent');
    // The unrelated legacy preference is left untouched rather than deleted.
    expect(localStorage.getItem(ACCENT_STORAGE_KEY)).toBe('rose');
  });

  it('renders only Light and Dark choices with no accent-colour selector', async () => {
    const user = userEvent.setup();
    const { container } = renderControl();

    const dialog = await openDialog(user);

    expect(within(dialog).queryAllByRole('radio')).toHaveLength(2);
    expect(within(dialog).queryByRole('radiogroup', { name: /accent/i })).toBeNull();
    expect(
      within(dialog).queryByRole('radio', { name: /green|blue|indigo|purple|rose|slate/i }),
    ).toBeNull();

    expect(container.querySelector('.accent-grid')).toBeNull();
    expect(container.querySelector('.accent-swatch')).toBeNull();
    expect(container.querySelector('[data-accent]')).toBeNull();
  });

  it('opens and switches appearance from the compact control', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    const user = userEvent.setup();
    renderControl('compact');

    expect(rootTheme()).toBe('dark');

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('radio', { name: 'Light' }));

    expect(rootTheme()).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('keeps the teal accent tokens unchanged while switching modes', async () => {
    const user = userEvent.setup();
    renderControl();

    const rootBlock = cssSource.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] ?? '';
    const darkBlock = cssSource.match(/\[data-theme='dark'\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? '';

    expect(rootBlock).toContain('--primary-rgb: 15 118 110');
    expect(rootBlock).toContain('--primary-text: #0f766e');
    expect(darkBlock).toContain('--primary-rgb: 45 212 191');
    expect(darkBlock).toContain('--primary-text: #5eead4');

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('radio', { name: 'Dark' }));

    expect(document.documentElement).not.toHaveAttribute('data-accent');
    expect(document.documentElement.style.getPropertyValue('--primary-rgb')).toBe('');

    await user.click(within(dialog).getByRole('radio', { name: 'Light' }));

    expect(document.documentElement).not.toHaveAttribute('data-accent');
    expect(document.documentElement.style.getPropertyValue('--primary-rgb')).toBe('');
  });

  it('removes palette switching from the stylesheet and pre-hydration script', () => {
    expect(cssSource).not.toMatch(/\[data-accent/);
    expect(cssSource).not.toContain('accent-swatch');
    expect(cssSource).not.toContain('accent-grid');
    expect(cssSource).not.toContain('--swatch');
    expect(htmlSource).not.toContain('verifygrid_accent');
    expect(htmlSource).not.toContain('data-accent');
    expect(htmlSource).not.toMatch(/validThemes|theme === 'system'|theme = 'system'/);
  });

  it('keeps sidebar navigation and the appearance control functional together', async () => {
    const user = userEvent.setup();
    const onSelectTab = vi.fn();
    render(
      <ThemeProvider>
        <Sidebar currentTab="projects" onSelectTab={onSelectTab} />
      </ThemeProvider>,
    );

    expect(screen.getByRole('button', { name: 'Projects' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Appearance settings' })).toHaveTextContent(
      /^AppearanceLight$/,
    );

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('radio', { name: 'Dark' }));
    expect(rootTheme()).toBe('dark');
    expect(screen.getByRole('button', { name: 'Appearance settings' })).toHaveTextContent(
      /^AppearanceDark$/,
    );

    await user.click(screen.getByRole('button', { name: 'Financial Auditing' }));
    expect(onSelectTab).toHaveBeenCalledWith('financial');

    await user.click(screen.getByRole('button', { name: 'Audit History' }));
    expect(onSelectTab).toHaveBeenCalledWith('runs');
  });
});
