import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Header } from '../src/shell/Header';
import { ComplianceFooter } from '../src/shell/ComplianceFooter';
import { Composer } from '../src/shell/Composer';
import { WidgetFrame } from '../src/shell/WidgetFrame';
import { AppSheet } from '../src/shell/AppSheet';
import { SupportEntry, SUPPORT_PLACEHOLDER } from '../src/entry/SupportEntry';
import { ReportsEntry, REPORTS_PLACEHOLDERS } from '../src/entry/ReportsEntry';

afterEach(() => localStorage.clear());

describe('header + footer + composer', () => {
  it('header shows the client id and fires Start over', async () => {
    const onStartOver = vi.fn();
    render(<Header clientId="X008593" onStartOver={onStartOver} />);
    expect(screen.getByText(/online · X008593/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Start over/ }));
    expect(onStartOver).toHaveBeenCalledOnce();
  });

  it('compliance footer is always present with both lines', () => {
    render(<ComplianceFooter />);
    expect(screen.getByText('Factual answers only — never investment advice.')).toBeInTheDocument();
    expect(screen.getByText('Files land right here — no email verification.')).toBeInTheDocument();
  });

  it('composer sends trimmed text and clears; disabled blocks send', async () => {
    const onSend = vi.fn();
    const { rerender } = render(<Composer placeholder="ask" onSend={onSend} />);
    const input = screen.getByRole('textbox', { name: 'Message' });
    await userEvent.type(input, '  hello  ');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSend).toHaveBeenCalledWith('hello');
    expect(input).toHaveValue('');

    rerender(<Composer placeholder="ask" onSend={onSend} disabled />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSend).toHaveBeenCalledTimes(1);
  });
});

describe('entry surfaces', () => {
  it('Support 1a uses the fixed FinX placeholder', () => {
    render(<SupportEntry onSend={() => {}} />);
    expect(screen.getByPlaceholderText(SUPPORT_PLACEHOLDER)).toBeInTheDocument();
  });

  it('Reports 1b starts on a rotating placeholder from the pool', () => {
    render(<ReportsEntry onSend={() => {}} />);
    expect(screen.getByPlaceholderText(REPORTS_PLACEHOLDERS[0])).toBeInTheDocument();
  });

  it('Reports 1b rotates the placeholder over time', () => {
    vi.useFakeTimers();
    try {
      render(<ReportsEntry onSend={() => {}} intervalMs={1000} />);
      expect(screen.getByPlaceholderText(REPORTS_PLACEHOLDERS[0])).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByPlaceholderText(REPORTS_PLACEHOLDERS[1])).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('web WidgetFrame', () => {
  it('collapses to a launcher and shows an unread badge for messages arriving while collapsed', async () => {
    const { rerender } = render(<WidgetFrame messageCount={2}>body</WidgetFrame>);
    expect(screen.getByTestId('jini-frame')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Minimize' }));
    // now collapsed -> launcher
    const launcher = screen.getByRole('button', { name: 'Open Choice Jini' });
    expect(launcher).toBeInTheDocument();
    // two more bot blocks arrive while collapsed
    rerender(<WidgetFrame messageCount={4}>body</WidgetFrame>);
    expect(screen.getByLabelText('2 unread messages')).toHaveTextContent('2');
    // reopening clears the unread badge
    await userEvent.click(screen.getByRole('button', { name: 'Open Choice Jini' }));
    expect(screen.queryByLabelText(/unread messages/)).not.toBeInTheDocument();
  });

  it('applies a persisted position from localStorage', () => {
    localStorage.setItem('jini-frame-pos', JSON.stringify({ x: 12, y: 34 }));
    render(<WidgetFrame messageCount={0}>body</WidgetFrame>);
    const frame = screen.getByTestId('jini-frame');
    expect(frame.style.left).toBe('12px');
    expect(frame.style.top).toBe('34px');
  });

  it('persists a dragged position to localStorage', () => {
    render(<WidgetFrame messageCount={0}>body</WidgetFrame>);
    const grip = screen.getByRole('separator', { name: 'Drag widget' });
    fireEvent.pointerDown(grip, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientX: 150, clientY: 130, pointerId: 1 });
    fireEvent.pointerUp(grip, { pointerId: 1 });
    const saved = JSON.parse(localStorage.getItem('jini-frame-pos')!);
    expect(saved).toMatchObject({ x: expect.any(Number), y: expect.any(Number) });
  });
});

describe('app WebView AppSheet', () => {
  it('renders a full-screen sheet', () => {
    render(<AppSheet>body</AppSheet>);
    const sheet = screen.getByTestId('jini-sheet');
    expect(sheet).toHaveClass('jini-sheet');
  });

  it('dismisses when swiped down past the threshold', () => {
    const onDismiss = vi.fn();
    render(<AppSheet onDismiss={onDismiss}>body</AppSheet>);
    const grip = screen.getByRole('separator', { name: 'Swipe down to dismiss' });
    fireEvent.pointerDown(grip, { clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientY: 130, pointerId: 1 });
    fireEvent.pointerUp(grip, { pointerId: 1 });
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('does not dismiss on a small drag', () => {
    const onDismiss = vi.fn();
    render(<AppSheet onDismiss={onDismiss}>body</AppSheet>);
    const grip = screen.getByRole('separator', { name: 'Swipe down to dismiss' });
    fireEvent.pointerDown(grip, { clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientY: 40, pointerId: 1 });
    fireEvent.pointerUp(grip, { pointerId: 1 });
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
