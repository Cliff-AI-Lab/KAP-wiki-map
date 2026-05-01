/**
 * LanguageSwitcher smoke test（M16 #1）。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LanguageSwitcher from './LanguageSwitcher';

const setLocaleMock = vi.fn();

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh',
    setLocale: setLocaleMock,
    t: (key: string) => key,
  }),
}));


describe('LanguageSwitcher', () => {
  it('renders both language buttons', () => {
    render(<LanguageSwitcher />);
    expect(screen.getByText('中')).toBeInTheDocument();
    expect(screen.getByText('EN')).toBeInTheDocument();
  });

  it('zh button is pressed when locale=zh', () => {
    render(<LanguageSwitcher />);
    const zhBtn = screen.getByText('中');
    expect(zhBtn.getAttribute('aria-pressed')).toBe('true');
  });

  it('clicking EN calls setLocale("en")', () => {
    setLocaleMock.mockReset();
    render(<LanguageSwitcher />);
    fireEvent.click(screen.getByText('EN'));
    expect(setLocaleMock).toHaveBeenCalledWith('en');
  });
});
