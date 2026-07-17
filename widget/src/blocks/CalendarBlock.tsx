import { useState } from 'react';
import type { CalendarBlock as CalendarWire, DateRange } from '../api/wireTypes';
import { useBlockActions } from './context';

const WD = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const pad = (n: number) => String(n).padStart(2, '0');
const iso = (y: number, m0: number, d: number) => `${y}-${pad(m0 + 1)}-${pad(d)}`;

/** ISO dates sort lexicographically == chronologically, so string compares are
 *  safe and timezone-free. A day is hard-disabled if it is outside
 *  [min_date, max_date] or inside any server-supplied disabled range. The widget
 *  OBEYS these bounds; it never computes or hardcodes per-flow windows. */
export function isOutOfRange(day: string, minDate: string, maxDate: string, disabled: DateRange[] = []): boolean {
  if (day < minDate || day > maxDate) return true;
  return disabled.some((r) => {
    const afterFrom = r.from == null || day >= r.from;
    const beforeTo = r.to == null || day <= r.to;
    return afterFrom && beforeTo;
  });
}

/** Days more than `maxRangeDays` AFTER a chosen range-start are disabled. Days
 *  before the start stay enabled so tapping one re-picks the start (otherwise
 *  a mis-tapped start would be a dead end). */
export function beyondMaxRange(day: string, start: string | null, maxRangeDays: number | null | undefined): boolean {
  if (start == null || maxRangeDays == null) return false;
  const s = new Date(start + 'T00:00:00Z').getTime();
  const d = new Date(day + 'T00:00:00Z').getTime();
  const spanDays = Math.round((d - s) / 86_400_000);
  return spanDays > maxRangeDays;
}

export function CalendarBlock({ block }: { block: CalendarWire }) {
  const { dispatch } = useBlockActions();
  const rangeMode = block.max_range_days != null;
  const initial = new Date(block.max_date + 'T00:00:00Z');
  const [view, setView] = useState({ y: initial.getUTCFullYear(), m: initial.getUTCMonth() });
  const [start, setStart] = useState<string | null>(null);

  const daysInMonth = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate();
  const firstWeekday = new Date(Date.UTC(view.y, view.m, 1)).getUTCDay();
  const cells: Array<number | null> = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const shift = (delta: number) => {
    const m = view.m + delta;
    setView({ y: view.y + Math.floor(m / 12), m: ((m % 12) + 12) % 12 });
  };

  const pick = (day: string) => {
    if (!rangeMode) {
      dispatch({ kind: 'select_param', payload: { step: 'date', value: day } });
      return;
    }
    if (start == null || day < start) {
      setStart(day);
      return;
    }
    dispatch({ kind: 'select_param', payload: { step: 'date_range', from: start, to: day } });
    setStart(null);
  };

  return (
    <div className="cal" role="group" aria-label="date picker">
      <div className="cal-h">
        <button type="button" className="nav" aria-label="Previous month" onClick={() => shift(-1)}>‹</button>
        <b>{MONTHS[view.m]} {view.y}</b>
        <button type="button" className="nav" aria-label="Next month" onClick={() => shift(1)}>›</button>
      </div>
      <div className="cal-g">
        {WD.map((w, i) => (
          <div className="wd" key={`wd-${i}`}>{w}</div>
        ))}
        {cells.map((day, i) => {
          if (day == null) return <div className="d off" key={`b-${i}`} aria-hidden="true" />;
          const dayIso = iso(view.y, view.m, day);
          const disabled = isOutOfRange(dayIso, block.min_date, block.max_date, block.disabled_ranges) || beyondMaxRange(dayIso, start, block.max_range_days);
          const selected = start === dayIso;
          return (
            <button
              type="button"
              key={dayIso}
              className={`d${disabled ? ' dis' : ''}${selected ? ' sel' : ''}`}
              disabled={disabled}
              aria-disabled={disabled}
              aria-label={dayIso}
              onClick={disabled ? undefined : () => pick(dayIso)}
            >
              {day}
            </button>
          );
        })}
      </div>
      <div className="cal-hint">△ Only the days you can pick are tappable — the rest are out of range.</div>
    </div>
  );
}
