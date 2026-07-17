import { useState } from 'react';
import type { NoteListCardBlock as NoteList, NoteRow } from '../api/wireTypes';
import { ChipButton } from './ChipButton';
import { useBlockActions } from './context';

const MONTHS: Record<string, string> = {
  Jan: 'January', Feb: 'February', Mar: 'March', Apr: 'April', May: 'May', Jun: 'June',
  Jul: 'July', Aug: 'August', Sep: 'September', Oct: 'October', Nov: 'November', Dec: 'December',
};

/** Derive the month-divider label from a row's date_label (e.g.
 *  "Mon, 14 Jul 2026" → "July 2026"). Falls back to the raw label. */
export function monthLabel(dateLabel: string): string {
  const m = dateLabel.match(/([A-Za-z]{3})[a-z]*\s+(\d{4})/);
  if (!m) return dateLabel;
  return `${MONTHS[m[1]] ?? m[1]} ${m[2]}`;
}

/** Paginate rows client-side into pages of `size`, revealing incrementally. */
export function pageWindow<T>(rows: T[], visible: number): T[] {
  return rows.slice(0, visible);
}

/** Contract-note list. Client-side pagination over the block's row array
 *  (page_size, default 10), month dividers, a segment badge only on dual-note
 *  rows, per-row download (opaque downloadToken — never a file_id), and
 *  footer actions (email-all). */
export function NoteListBlock({ block }: { block: NoteList }) {
  const { dispatch } = useBlockActions();
  const pageSize = block.page_size ?? 10;
  const [visible, setVisible] = useState(pageSize);
  const rows = pageWindow(block.rows, visible);
  const remaining = block.rows.length - rows.length;

  let lastMonth = '';
  return (
    <div className="notelist">
      {rows.map((row: NoteRow, i) => {
        const month = monthLabel(row.date_label);
        const divider = month !== lastMonth ? month : null;
        lastMonth = month;
        const mcx = row.segment_badge === 'MCX';
        return (
          <div key={`${row.downloadToken}-${i}`}>
            {divider && <div className="nl-div">{divider}</div>}
            <div className="nl-row">
              <div className="nl-day">{row.date_label}</div>
              {row.segment_badge && (
                <span className={mcx ? 'nl-badge mcx' : 'nl-badge'}>{row.segment_badge}</span>
              )}
              <button
                type="button"
                className="nl-dl"
                aria-label={`Download ${row.date_label}`}
                onClick={() => dispatch({ kind: 'deep_link', payload: { download_token: row.downloadToken } })}
              >
                Get it here
              </button>
            </div>
          </div>
        );
      })}
      {remaining > 0 && (
        <button type="button" className="nl-more" onClick={() => setVisible((v) => v + pageSize)}>
          Show more ({remaining} remaining)
        </button>
      )}
      {block.footer_chips && block.footer_chips.length > 0 && (
        <div className="nl-foot">
          {block.footer_chips.map((chip, i) => (
            <ChipButton key={`${chip.label}-${i}`} chip={chip} primary={i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}
