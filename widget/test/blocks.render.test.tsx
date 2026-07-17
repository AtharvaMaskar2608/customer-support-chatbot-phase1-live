import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { BlockActionsContext } from '../src/blocks/context';
import { RenderBlock } from '../src/blocks/RenderBlock';
import type { Block, ChipAction } from '../src/api/wireTypes';
import { ALL_BLOCK_FIXTURES, EXTRA_FIXTURES } from '../mock/fixtures/blocks';

function renderBlock(block: Block, dispatch: (a: ChipAction) => void = () => {}) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <BlockActionsContext.Provider value={{ dispatch }}>{children}</BlockActionsContext.Provider>
  );
  return render(<RenderBlock block={block} />, { wrapper });
}

describe('every wire block renders from its fixture', () => {
  it('bubble shows bot text', () => {
    renderBlock(ALL_BLOCK_FIXTURES.bubble);
    expect(screen.getByText(/which segment/i)).toBeInTheDocument();
  });

  it('user_bubble shows the echoed user text', () => {
    renderBlock(ALL_BLOCK_FIXTURES.user_bubble);
    expect(screen.getByText('Get my P&L')).toBeInTheDocument();
  });

  it('chip_row renders all chips as buttons', () => {
    renderBlock(ALL_BLOCK_FIXTURES.chip_row);
    expect(screen.getByRole('button', { name: /Get my P&L/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /brokerage charges/ })).toBeInTheDocument();
  });

  it('stepper_card shows the active step chips', () => {
    renderBlock(ALL_BLOCK_FIXTURES.stepper_card);
    expect(screen.getByRole('button', { name: 'Equity' })).toBeInTheDocument();
    expect(screen.getByText('1 · Segment')).toBeInTheDocument();
  });

  it('calendar renders a month grid with disabled out-of-range days', () => {
    renderBlock(ALL_BLOCK_FIXTURES.calendar);
    // 2026-07-17..31 are in a disabled range -> hard-disabled buttons
    const d17 = screen.getByRole('button', { name: '2026-07-17' });
    expect(d17).toBeDisabled();
    const d16 = screen.getByRole('button', { name: '2026-07-16' });
    expect(d16).not.toBeDisabled();
  });

  it('file_card shows filename, size/format/password sub, and actions', () => {
    renderBlock(ALL_BLOCK_FIXTURES.file_card);
    expect(screen.getByText('PnL_Equity_FY2025-26.pdf')).toBeInTheDocument();
    expect(screen.getByText('196 KB · PDF · password: PAN')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Trouble opening it/ })).toBeInTheDocument();
  });

  it('note_list_card renders rows, a month divider, and a segment badge', () => {
    renderBlock(ALL_BLOCK_FIXTURES.note_list_card);
    expect(screen.getByText('July 2026')).toBeInTheDocument();
    expect(screen.getByText('Mon, 14 Jul 2026')).toBeInTheDocument();
    expect(screen.getByText('MCX')).toBeInTheDocument();
  });

  it('data_card renders dynamic groups and verbatim values', () => {
    renderBlock(ALL_BLOCK_FIXTURES.data_card);
    expect(screen.getByText('Equity')).toBeInTheDocument();
    expect(screen.getByText('₹0.10 for trade value of 10 thousand')).toBeInTheDocument();
  });

  it('error_bubble shows code and recovery chips (not a toast)', () => {
    renderBlock(ALL_BLOCK_FIXTURES.error_bubble);
    expect(screen.getByText(/E-NODATA/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Raise a ticket/ })).toBeInTheDocument();
  });

  it('ticket_confirmation shows the ticket id and message', () => {
    renderBlock(ALL_BLOCK_FIXTURES.ticket_confirmation);
    expect(screen.getByText('#48211')).toBeInTheDocument();
    expect(screen.getByText(/within 24 hours/)).toBeInTheDocument();
  });

  it('generating shows the latency indicator', () => {
    renderBlock(ALL_BLOCK_FIXTURES.generating);
    expect(screen.getByRole('status')).toHaveTextContent('Generating…');
  });
});

describe('RenderBlock forward-compatibility', () => {
  it('renders nothing for an unknown block type (safe no-op)', () => {
    const { container } = renderBlock({ type: 'future_block' } as unknown as Block);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('extra fixtures', () => {
  it('compliance bubble renders the disclaimer + trust line', () => {
    renderBlock(EXTRA_FIXTURES.complianceBubble);
    expect(screen.getAllByText(/never investment advice/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/no email verification/)).toBeInTheDocument();
  });

  it('CML file card has no password sub', () => {
    renderBlock(EXTRA_FIXTURES.cmlFileCard);
    expect(screen.getByText('Client_Master_List.pdf')).toBeInTheDocument();
    expect(screen.getByText('9 KB · PDF')).toBeInTheDocument();
  });
});

describe('chip taps dispatch the server action verbatim', () => {
  it('dispatches the chip action on click', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const dispatch = vi.fn();
    renderBlock(ALL_BLOCK_FIXTURES.chip_row, dispatch);
    await userEvent.click(screen.getByRole('button', { name: /Get my P&L/ }));
    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'send_text', payload: expect.objectContaining({ intent: 'report_pnl' }) }),
    );
  });

  it('file helper link emits a clarification turn', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const dispatch = vi.fn();
    renderBlock(ALL_BLOCK_FIXTURES.file_card, dispatch);
    await userEvent.click(screen.getByRole('button', { name: /Trouble opening it/ }));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ kind: 'send_text' }));
  });
});
