import type { Block } from '../api/wireTypes';
import { BubbleBlock, UserBubbleBlock } from './BubbleBlock';
import { ChipRowBlock } from './ChipRowBlock';
import { StepperCardBlock } from './StepperCardBlock';
import { CalendarBlock } from './CalendarBlock';
import { FileCardBlock } from './FileCardBlock';
import { NoteListBlock } from './NoteListBlock';
import { DataCardBlock } from './DataCardBlock';
import { ErrorBubbleBlock } from './ErrorBubbleBlock';
import { TicketConfirmationBlock } from './TicketConfirmationBlock';
import { GeneratingBlockView } from './GeneratingIndicator';

/**
 * Discriminated-union switch: one render-block component per wire `type`. The
 * widget renders exactly the blocks the server sends, in order — it never
 * synthesizes or reorders. An unrecognized type is a safe no-op (forward
 * compatibility) rather than a crash.
 */
export function RenderBlock({ block }: { block: Block }) {
  switch (block.type) {
    case 'bubble':
      return <BubbleBlock block={block} />;
    case 'user_bubble':
      return <UserBubbleBlock block={block} />;
    case 'chip_row':
      return <ChipRowBlock block={block} />;
    case 'stepper_card':
      return <StepperCardBlock block={block} />;
    case 'calendar':
      return <CalendarBlock block={block} />;
    case 'file_card':
      return <FileCardBlock block={block} />;
    case 'note_list_card':
      return <NoteListBlock block={block} />;
    case 'data_card':
      return <DataCardBlock block={block} />;
    case 'error_bubble':
      return <ErrorBubbleBlock block={block} />;
    case 'ticket_confirmation':
      return <TicketConfirmationBlock block={block} />;
    case 'generating':
      return <GeneratingBlockView block={block} />;
    default:
      return null;
  }
}
