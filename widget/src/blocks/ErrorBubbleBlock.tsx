import type { ErrorBubbleBlock as ErrorBubble, ErrorCode } from '../api/wireTypes';
import { ChipButton } from './ChipButton';

// Severity is derived from the code (the wire type carries no severity field):
// hard failures read as danger, recoverable/empty states as warn.
const DANGER: ReadonlySet<ErrorCode> = new Set<ErrorCode>(['E-FETCH', 'E-UNKNOWN']);

/** Conversational error — never a toast. Code, copy, and recovery chips come
 *  verbatim from the server; the widget renders, it does not author copy. */
export function ErrorBubbleBlock({ block }: { block: ErrorBubble }) {
  const danger = DANGER.has(block.code);
  return (
    <div className="msg l">
      <div className={`bub bot errbub${danger ? ' danger' : ''}`}>
        <div className="etag">
          {danger ? '⚠' : '△'} {block.code}
        </div>
        {block.text}
        {block.chips && block.chips.length > 0 && (
          <div className="chips">
            {block.chips.map((chip, i) => (
              <ChipButton key={`${chip.label}-${i}`} chip={chip} primary={i === 0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
