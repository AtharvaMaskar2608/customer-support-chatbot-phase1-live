import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { BlockActionsContext } from '../src/blocks/context';
import { RenderBlock } from '../src/blocks/RenderBlock';
import { isOutOfRange, beyondMaxRange } from '../src/blocks/CalendarBlock';
import { monthLabel } from '../src/blocks/NoteListBlock';
import { handleChat, resetMock } from '../mock/server';
import type { Block, ChipAction, DataCardBlock, StepperCardBlock, CalendarBlock, SessionContext, StepperCard } from '../src/api/wireTypes';

function renderBlock(block: Block, dispatch: (a: ChipAction) => void = () => {}) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <BlockActionsContext.Provider value={{ dispatch }}>{children}</BlockActionsContext.Provider>
  );
  return render(<RenderBlock block={block} />, { wrapper });
}

const session: SessionContext = {
  user_id: 'X008593', session_id: 's', access_token: 't',
  platform: 'web', page: 'support', entry_surface: 'support', is_dark_theme: false,
};

// ---- 1. Stepper edit clears downstream selections -------------------------

describe('stepper edit', () => {
  it('tapping a done step dispatches a reopen turn for that step id', async () => {
    const dispatch = vi.fn();
    const stepper: StepperCardBlock = {
      type: 'stepper_card',
      steps: [
        { id: 'segment', title: '1 · Segment', state: 'done', selected_label: 'Equity' },
        { id: 'period', title: '2 · Date range', state: 'active', chips: [] },
        { id: 'format', title: '3 · How do you want it?', state: 'pending' },
      ],
    };
    renderBlock(stepper, dispatch);
    await userEvent.click(screen.getByRole('button', { name: /Edit 1 · Segment/ }));
    expect(dispatch).toHaveBeenCalledWith({ kind: 'select_param', payload: { step: 'segment', reopen: '1' } });
  });

  it('server clears all downstream selections when a done step is reopened', () => {
    resetMock();
    const seed = handleChat({ session, turn_number: 0 });
    const tid = seed.thread_id;
    handleChat({ session, thread_id: tid, turn_number: 1, message: 'Get my P&L' });
    handleChat({ session, thread_id: tid, turn_number: 2, action: { kind: 'select_param', payload: { flow: 'pnl', step: 'segment', value: 'Equity' } } });
    handleChat({ session, thread_id: tid, turn_number: 3, action: { kind: 'select_param', payload: { flow: 'pnl', step: 'period', value: 'This FY' } } });
    // Reopen the first step — downstream (period, format) must clear.
    const reopened = handleChat({ session, thread_id: tid, turn_number: 4, action: { kind: 'select_param', payload: { flow: 'pnl', step: 'segment', reopen: '1' } } });
    const stepper = reopened.blocks.find((b): b is StepperCard => b.type === 'stepper_card')!;
    const byId = Object.fromEntries(stepper.steps.map((s) => [s.id, s]));
    expect(byId.segment.state).toBe('active');
    expect(byId.segment.selected_label ?? null).toBeNull();
    expect(byId.period.state).toBe('pending');
    expect(byId.period.selected_label ?? null).toBeNull();
    expect(byId.format.state).toBe('pending');
  });
});

// ---- 2. Calendar hard-disables out-of-range days --------------------------

describe('calendar hard-disable', () => {
  it('isOutOfRange respects min/max and disabled ranges', () => {
    expect(isOutOfRange('2017-12-31', '2018-01-01', '2026-07-16')).toBe(true); // before min
    expect(isOutOfRange('2026-07-17', '2018-01-01', '2026-07-16')).toBe(true); // after max
    expect(isOutOfRange('2020-06-15', '2018-01-01', '2026-07-16')).toBe(false);
    expect(isOutOfRange('2026-07-20', '2018-01-01', '2026-07-31', [{ from: '2026-07-17', to: '2026-07-25' }])).toBe(true);
  });

  it('beyondMaxRange disables days more than maxRangeDays after the start', () => {
    expect(beyondMaxRange('2026-07-10', '2026-07-01', 7)).toBe(true); // 9 days out
    expect(beyondMaxRange('2026-07-05', '2026-07-01', 7)).toBe(false);
    expect(beyondMaxRange('2026-07-05', null, 7)).toBe(false); // no start
    expect(beyondMaxRange('2026-07-05', '2026-07-01', null)).toBe(false); // no cap
  });

  it('renders disabled days as non-clickable (no dispatch on tap)', async () => {
    const dispatch = vi.fn();
    const cal: CalendarBlock = {
      type: 'calendar', min_date: '2026-07-01', max_date: '2026-07-16', max_range_days: null,
      disabled_ranges: [{ from: '2026-07-17', to: '2026-07-31' }],
    };
    renderBlock(cal, dispatch);
    const disabledDay = screen.getByRole('button', { name: '2026-07-20' });
    expect(disabledDay).toBeDisabled();
    await userEvent.click(disabledDay);
    expect(dispatch).not.toHaveBeenCalled();
    // an in-range day IS clickable and dispatches a date pick
    await userEvent.click(screen.getByRole('button', { name: '2026-07-10' }));
    expect(dispatch).toHaveBeenCalledWith({ kind: 'select_param', payload: { step: 'date', value: '2026-07-10' } });
  });

  it('range mode disables days beyond the cap once a start is picked', async () => {
    const dispatch = vi.fn();
    const cal: CalendarBlock = {
      type: 'calendar', min_date: '2026-07-01', max_date: '2026-07-31', max_range_days: 7,
      disabled_ranges: [],
    };
    renderBlock(cal, dispatch);
    await userEvent.click(screen.getByRole('button', { name: '2026-07-05' })); // start
    expect(dispatch).not.toHaveBeenCalled(); // range not complete yet
    expect(screen.getByRole('button', { name: '2026-07-20' })).toBeDisabled(); // 15 days > cap
    await userEvent.click(screen.getByRole('button', { name: '2026-07-10' })); // end within cap
    expect(dispatch).toHaveBeenCalledWith({ kind: 'select_param', payload: { step: 'date_range', from: '2026-07-05', to: '2026-07-10' } });
  });
});

// ---- 3. Note-list pagination + dividers + conditional badge ---------------

describe('note-list pagination', () => {
  const build = (n: number): Block => ({
    type: 'note_list_card',
    page_size: 10,
    total: n,
    rows: Array.from({ length: n }, (_, i) => ({
      date_label: `Day ${i + 1}, ${i < 7 ? 'Jul' : 'Jun'} 2026`,
      weekday: 'Monday',
      downloadToken: `tok-${i}`,
      ...(i === 1 ? { segment_badge: 'MCX' } : {}),
    })),
  });

  it('shows page_size rows first, then reveals the rest on Show more', async () => {
    renderBlock(build(12));
    expect(screen.getAllByRole('button', { name: /^Download / })).toHaveLength(10);
    const more = screen.getByRole('button', { name: /Show more \(2 remaining\)/ });
    await userEvent.click(more);
    expect(screen.getAllByRole('button', { name: /^Download / })).toHaveLength(12);
    expect(screen.queryByText(/Show more/)).not.toBeInTheDocument();
  });

  it('renders month dividers and a segment badge only on the dual-note row', () => {
    renderBlock(build(12));
    expect(screen.getByText('July 2026')).toBeInTheDocument();
    expect(screen.getByText('June 2026')).toBeInTheDocument();
    // exactly one badge across the first page (only row index 1 has one)
    expect(screen.getAllByText('MCX')).toHaveLength(1);
  });

  it('monthLabel expands the abbreviation', () => {
    expect(monthLabel('Mon, 14 Jul 2026')).toBe('July 2026');
    expect(monthLabel('Fri, 27 Jun 2026')).toBe('June 2026');
  });

  it('uses the server-supplied month_dividers text for section headers', () => {
    const block: Block = {
      type: 'note_list_card',
      page_size: 10,
      total: 3,
      month_dividers: ['JULY — server', 'JUNE — server'],
      rows: [
        { date_label: 'Mon, 14 Jul 2026', weekday: 'Monday', downloadToken: 't1' },
        { date_label: 'Wed, 9 Jul 2026', weekday: 'Wednesday', downloadToken: 't2' },
        { date_label: 'Fri, 27 Jun 2026', weekday: 'Friday', downloadToken: 't3' },
      ],
    };
    renderBlock(block);
    expect(screen.getByText('JULY — server')).toBeInTheDocument();
    expect(screen.getByText('JUNE — server')).toBeInTheDocument();
    expect(screen.queryByText('July 2026')).not.toBeInTheDocument();
  });

  it('does not emit a divider per row for non-standard date labels', () => {
    const block: Block = {
      type: 'note_list_card',
      page_size: 10,
      total: 3,
      rows: [
        { date_label: '2026-07-14', weekday: 'Monday', downloadToken: 't1' },
        { date_label: '2026-07-09', weekday: 'Wednesday', downloadToken: 't2' },
        { date_label: '2026-06-27', weekday: 'Friday', downloadToken: 't3' },
      ],
    };
    const { container } = renderBlock(block);
    // ISO labels don't parse to a month key -> at most one divider, never one per row
    expect(container.querySelectorAll('.nl-div').length).toBeLessThanOrEqual(1);
  });

  it('page_size <= 0 does not deadlock (falls back to a usable page size)', () => {
    const block: Block = {
      type: 'note_list_card',
      page_size: 0,
      total: 3,
      rows: [
        { date_label: 'Mon, 14 Jul 2026', weekday: 'Monday', downloadToken: 't1' },
        { date_label: 'Wed, 9 Jul 2026', weekday: 'Wednesday', downloadToken: 't2' },
        { date_label: 'Fri, 27 Jun 2026', weekday: 'Friday', downloadToken: 't3' },
      ],
    };
    renderBlock(block);
    expect(screen.getAllByRole('button', { name: /^Download / })).toHaveLength(3);
    expect(screen.queryByText(/Show more/)).not.toBeInTheDocument();
  });
});

describe('calendar range mode reset', () => {
  it('tapping an earlier day re-picks the range start instead of dead-ending', async () => {
    const dispatch = vi.fn();
    const cal: CalendarBlock = {
      type: 'calendar', min_date: '2026-07-01', max_date: '2026-07-31', max_range_days: 30,
      disabled_ranges: [],
    };
    renderBlock(cal, dispatch);
    await userEvent.click(screen.getByRole('button', { name: '2026-07-15' })); // first start
    const earlier = screen.getByRole('button', { name: '2026-07-05' });
    expect(earlier).not.toBeDisabled(); // earlier days stay enabled
    await userEvent.click(earlier); // re-pick start earlier
    expect(dispatch).not.toHaveBeenCalled(); // still just a start, no range yet
    await userEvent.click(screen.getByRole('button', { name: '2026-07-10' })); // end
    expect(dispatch).toHaveBeenCalledWith({ kind: 'select_param', payload: { step: 'date_range', from: '2026-07-05', to: '2026-07-10' } });
  });
});

// ---- 4. Data-card renders arbitrary dynamic groups ------------------------

describe('data-card is fully dynamic', () => {
  it('renders arbitrary groups/rows verbatim with no hardcoded structure', () => {
    const card: DataCardBlock = {
      type: 'data_card',
      groups: [
        { title: 'Zeta Segment', list: [{ label: 'Made-up row', value: '₹123.45 arbitrary' }] },
        { title: 'Another Group', list: [
          { label: 'k1', value: 'v1' },
          { label: 'k2', value: 'v2' },
        ] },
      ],
    };
    renderBlock(card);
    expect(screen.getByText('Zeta Segment')).toBeInTheDocument();
    expect(screen.getByText('₹123.45 arbitrary')).toBeInTheDocument();
    expect(screen.getByText('Another Group')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
  });
});
