import { useEffect, useRef, useState, type ReactNode, type PointerEvent as ReactPointerEvent } from 'react';
import { usePersistedState } from './usePersistedState';

interface Pos {
  x: number;
  y: number;
}

/**
 * Web shell — a WhatsApp-style floating window (~400×640) bottom-right. Collapses
 * to a launcher bubble that carries an unread badge for bot messages that arrived
 * while collapsed; its dragged position persists in localStorage. Chosen for
 * `platform === 'web'`.
 */
export function WidgetFrame({ children, messageCount }: { children: ReactNode; messageCount: number }) {
  const [open, setOpen] = usePersistedState<boolean>('jini-frame-open', true);
  const [pos, setPos] = usePersistedState<Pos | null>('jini-frame-pos', null);
  const [seen, setSeen] = useState(messageCount);
  const drag = useRef<{ dx: number; dy: number } | null>(null);

  useEffect(() => {
    if (open) setSeen(messageCount);
  }, [open, messageCount]);

  const unread = open ? 0 : Math.max(0, messageCount - seen);
  const style = pos ? { left: pos.x, top: pos.y, right: 'auto', bottom: 'auto' } : undefined;

  const onGripDown = (e: ReactPointerEvent) => {
    const frame = (e.currentTarget as HTMLElement).closest('.jini-frame') as HTMLElement | null;
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    drag.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onGripMove = (e: ReactPointerEvent) => {
    if (!drag.current) return;
    setPos({ x: e.clientX - drag.current.dx, y: e.clientY - drag.current.dy });
  };
  const onGripUp = (e: ReactPointerEvent) => {
    drag.current = null;
    (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
  };

  if (!open) {
    return (
      <button
        type="button"
        className="jini-launcher"
        style={style}
        aria-label="Open Choice Jini"
        onClick={() => setOpen(true)}
      >
        ✦
        {unread > 0 && (
          <span className="jini-unread" aria-label={`${unread} unread messages`}>
            {unread}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="jini-frame" style={style} data-testid="jini-frame">
      <div
        className="jini-grip"
        role="separator"
        aria-label="Drag widget"
        onPointerDown={onGripDown}
        onPointerMove={onGripMove}
        onPointerUp={onGripUp}
      >
        <button type="button" className="jini-collapse" aria-label="Minimize" onClick={() => setOpen(false)}>
          –
        </button>
      </div>
      <div className="jini-frame-inner">{children}</div>
    </div>
  );
}
