import type { Chip } from '../api/wireTypes';
import { useBlockActions } from './context';

/** A single quick-reply chip. Tapping dispatches the chip's server-authored
 *  action verbatim — the widget adds no client-side routing logic. */
export function ChipButton({ chip, primary = false }: { chip: Chip; primary?: boolean }) {
  const { dispatch } = useBlockActions();
  return (
    <button
      type="button"
      className={primary ? 'chip primary' : 'chip'}
      onClick={() => dispatch(chip.action)}
    >
      {chip.label}
    </button>
  );
}
