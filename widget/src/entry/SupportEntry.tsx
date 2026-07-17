import { Composer } from '../shell/Composer';

export const SUPPORT_PLACEHOLDER = 'Ask anything about FinX…';

/** Entry 1a — Support section. The greeting + "Popular right now" chips arrive
 *  as seed blocks (config_slice); the surface-specific piece here is the fixed
 *  free-text composer placeholder. */
export function SupportEntry({ onSend, disabled }: { onSend: (t: string) => void; disabled?: boolean }) {
  return <Composer placeholder={SUPPORT_PLACEHOLDER} onSend={onSend} disabled={disabled} />;
}
