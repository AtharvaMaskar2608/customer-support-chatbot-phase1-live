import type { GeneratingBlock } from '../api/wireTypes';

/** "Generating…" latency indicator. Rendered both as a server `generating`
 *  block and by the shell when an in-flight turn exceeds 5s (spec §8.2). */
export function GeneratingIndicator({ message = 'Generating…' }: { message?: string }) {
  return (
    <div className="generating" role="status" aria-live="polite">
      <span className="gdots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {message}
    </div>
  );
}

export function GeneratingBlockView({ block }: { block: GeneratingBlock }) {
  return <GeneratingIndicator message={block.message} />;
}
