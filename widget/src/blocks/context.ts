import { createContext, useContext } from 'react';
import type { ChipAction } from '../api/wireTypes';

/**
 * The single dispatch a render block may call to start a new turn. Every
 * interactive block (chip tap, stepper edit, calendar pick, file/note action)
 * routes through this — it maps to Conversation.act(). Blocks NEVER fetch,
 * hold report URLs, or reach any endpoint directly.
 */
export interface BlockActions {
  dispatch: (action: ChipAction) => void;
}

const noop: BlockActions = { dispatch: () => {} };

export const BlockActionsContext = createContext<BlockActions>(noop);

export function useBlockActions(): BlockActions {
  return useContext(BlockActionsContext);
}
