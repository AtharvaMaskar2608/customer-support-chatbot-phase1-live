import { useEffect, useState } from 'react';
import { Composer } from '../shell/Composer';

/** Reports 1b rotating input placeholder pool — teaches the long-tail report
 *  sub-types (5–11) that don't fit the 4-chip limit. */
export const REPORTS_PLACEHOLDERS = [
  'or type: CML, Contract Note, Capital Gain, Global…',
  'or type: MTF Ledger, Tax P&L, Brokerage…',
  'or type: Holding, Ledger, P&L…',
];

/** Entry 1b — Reports screen. Fulfilment chips arrive as seed blocks; the
 *  surface-specific piece is the rotating composer placeholder. */
export function ReportsEntry({
  onSend,
  disabled,
  intervalMs = 4000,
}: {
  onSend: (t: string) => void;
  disabled?: boolean;
  intervalMs?: number;
}) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % REPORTS_PLACEHOLDERS.length), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return <Composer placeholder={REPORTS_PLACEHOLDERS[i]} onSend={onSend} disabled={disabled} />;
}
