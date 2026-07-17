import { useRef, useState, type ReactNode, type PointerEvent as ReactPointerEvent } from 'react';

const DISMISS_THRESHOLD = 90; // px dragged down before dismiss fires

/**
 * App WebView shell — full-screen, slides up (280ms) on mount, dismissable by
 * swiping down from the top grip. Chosen for `platform === 'webview'`.
 */
export function AppSheet({ children, onDismiss }: { children: ReactNode; onDismiss?: () => void }) {
  const startY = useRef<number | null>(null);
  const delta = useRef(0);
  const [dragY, setDragY] = useState(0);

  const onDown = (e: ReactPointerEvent) => {
    startY.current = e.clientY;
    delta.current = 0;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: ReactPointerEvent) => {
    if (startY.current == null) return;
    const d = Math.max(0, e.clientY - startY.current);
    delta.current = d;
    setDragY(d);
  };
  const onUp = () => {
    if (delta.current > DISMISS_THRESHOLD) onDismiss?.();
    startY.current = null;
    delta.current = 0;
    setDragY(0);
  };

  return (
    <div
      className="jini-sheet"
      data-testid="jini-sheet"
      style={dragY > 0 ? { transform: `translateY(${dragY}px)` } : undefined}
    >
      <div
        className="jini-sheet-grip"
        role="separator"
        aria-label="Swipe down to dismiss"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
      >
        <span className="jini-sheet-handle" />
      </div>
      <div className="jini-sheet-inner">{children}</div>
    </div>
  );
}
