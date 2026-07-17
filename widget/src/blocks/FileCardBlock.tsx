import type { FileCardBlock as FileCard } from '../api/wireTypes';
import { useBlockActions } from './context';

/** A delivered report file. Actions are server-driven tokens (download/email);
 *  the widget never holds a report URL or file_id. The "Trouble opening it?"
 *  helper emits a clarification turn. */
export function FileCardBlock({ block }: { block: FileCard }) {
  const { dispatch } = useBlockActions();
  const kind = block.format === 'xlsx' ? 'xls' : 'pdf';
  const sub = [block.size_label, block.format.toUpperCase(), block.password_hint]
    .filter(Boolean)
    .join(' · ');

  return (
    <div>
      <div className="filecard">
        <div className={`ficon ${kind}`}>{kind === 'xls' ? 'XLS' : 'PDF'}</div>
        <div className="fmeta">
          <div className="fname" title={block.filename}>{block.filename}</div>
          <div className="fsub">{sub}</div>
          {block.actions && block.actions.length > 0 && (
            <div className="facts">
              {block.actions.map((a, i) => (
                <button
                  key={`${a.label}-${i}`}
                  type="button"
                  className={i === 0 ? 'fa solid' : 'fa'}
                  onClick={() => dispatch(a.action)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <button
        type="button"
        className="flink"
        onClick={() => dispatch({ kind: 'send_text', payload: { text: block.helper ?? 'Trouble opening it? Tell me.' } })}
      >
        {block.helper ?? 'Trouble opening it? Tell me.'}
      </button>
    </div>
  );
}
