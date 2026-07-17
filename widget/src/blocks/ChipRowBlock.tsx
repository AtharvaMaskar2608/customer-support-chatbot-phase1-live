import type { ChipRowBlock as ChipRow } from '../api/wireTypes';
import { ChipButton } from './ChipButton';

/** A wrapping row of quick-reply chips. */
export function ChipRowBlock({ block }: { block: ChipRow }) {
  return (
    <div className="chips">
      {block.chips.map((chip, i) => (
        <ChipButton key={`${chip.label}-${i}`} chip={chip} primary={i === 0} />
      ))}
    </div>
  );
}
