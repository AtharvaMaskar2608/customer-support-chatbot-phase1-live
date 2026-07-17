import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse, delay } from 'msw';
import { App } from '../src/App';
import { resetMock, handleChat } from '../mock/server';
import { mswServer } from './msw';
import type { ChatRequest } from '../src/api/wireTypes';

function setUrl(search: string) {
  window.history.replaceState({}, '', `/${search}`);
}

beforeEach(() => {
  resetMock();
  document.documentElement.removeAttribute('data-theme');
});

describe('App integration against the mock', () => {
  it('boots the web frame, seeds the support entry, and shows chrome', async () => {
    setUrl('?userId=X008593&page=support&platform=web&isDarkTheme=false');
    render(<App />);
    // seed entry chips arrive from config_slice
    expect(await screen.findByRole('button', { name: /Get my P&L/ })).toBeInTheDocument();
    expect(screen.getByTestId('jini-frame')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ask anything about FinX…')).toBeInTheDocument();
    expect(screen.getByText('Factual answers only — never investment advice.')).toBeInTheDocument();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('renders the app WebView sheet and reports entry for a webview/reports handoff', async () => {
    setUrl('?userId=X008593&page=reports&platform=webview');
    render(<App />);
    expect(await screen.findByRole('button', { name: /P&L Statement/ })).toBeInTheDocument();
    expect(screen.getByTestId('jini-sheet')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/or type:/)).toBeInTheDocument();
  });

  it('runs a full turn: typing a message advances to the P&L stepper', async () => {
    setUrl('?userId=X008593&page=support&platform=web');
    render(<App />);
    await screen.findByRole('button', { name: /Get my P&L/ });
    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'Get my P&L');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    // server echoes the user turn and returns the stepper with segment chips
    expect(await screen.findByRole('button', { name: 'Equity' })).toBeInTheDocument();
    expect(screen.getByText('1 · Segment')).toBeInTheDocument();
  });

  it('tapping an entry chip walks the stepper to a delivered file card', async () => {
    setUrl('?userId=X008593&page=support&platform=web');
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: /Get my P&L/ }));
    await userEvent.click(await screen.findByRole('button', { name: 'Equity' }));
    await userEvent.click(await screen.findByRole('button', { name: 'This FY' }));
    await userEvent.click(await screen.findByRole('button', { name: 'PDF' }));
    expect(await screen.findByText('PnL_Equity_FY2025-26.pdf')).toBeInTheDocument();
  });

  it('shows the Generating indicator while a turn exceeds the slow threshold (>5s)', async () => {
    // Delay the seed response so the slow timer (here 20ms) fires first.
    mswServer.use(
      http.post('*/api/chat', async ({ request }) => {
        await delay(80);
        return HttpResponse.json(handleChat((await request.json()) as ChatRequest));
      }),
    );
    setUrl('?userId=X008593&page=support&platform=web');
    render(<App slowMs={20} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Generating…');
    // once the turn completes the indicator is gone and the seed rendered
    expect(await screen.findByRole('button', { name: /Get my P&L/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
  });

  it('swiping the app sheet down past the threshold dismisses the widget', async () => {
    const post = vi.fn();
    window.addEventListener('message', post);
    setUrl('?userId=X008593&page=reports&platform=webview');
    render(<App />);
    const sheet = await screen.findByTestId('jini-sheet');
    expect(sheet).toBeInTheDocument();
    const grip = screen.getByRole('separator', { name: 'Swipe down to dismiss' });
    fireEvent.pointerDown(grip, { clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientY: 140, pointerId: 1 });
    fireEvent.pointerUp(grip, { pointerId: 1 });
    await waitFor(() => expect(screen.queryByTestId('jini-sheet')).not.toBeInTheDocument());
    window.removeEventListener('message', post);
  });
});
