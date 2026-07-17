// The widget's typed view of the frozen chat-wire-api contract.
//
// `wireTypes.generated.ts` is produced verbatim from
// app/contracts/schema/chat_wire.schema.json by `npm run gen:types` and is the
// single source of truth. This module re-exports it and adds a discriminated
// `Block` union whose `type` field is REQUIRED so `switch (block.type)` narrows
// (the generated interfaces mark `type` optional because the Pydantic schema
// gives it a default). It never redefines a field — it only narrows the
// discriminant. If the contract changes, regenerate; do not hand-edit shapes.

export * from './wireTypes.generated';

import type {
  Bubble,
  UserBubble,
  ChipRow,
  StepperCard,
  Calendar,
  FileCard,
  NoteListCard,
  DataCard,
  ErrorBubble,
  TicketConfirmation,
  Generating,
  ChatResponse,
} from './wireTypes.generated';

export type BubbleBlock = Bubble & { type: 'bubble' };
export type UserBubbleBlock = UserBubble & { type: 'user_bubble' };
export type ChipRowBlock = ChipRow & { type: 'chip_row' };
export type StepperCardBlock = StepperCard & { type: 'stepper_card' };
export type CalendarBlock = Calendar & { type: 'calendar' };
export type FileCardBlock = FileCard & { type: 'file_card' };
export type NoteListCardBlock = NoteListCard & { type: 'note_list_card' };
export type DataCardBlock = DataCard & { type: 'data_card' };
export type ErrorBubbleBlock = ErrorBubble & { type: 'error_bubble' };
export type TicketConfirmationBlock = TicketConfirmation & { type: 'ticket_confirmation' };
export type GeneratingBlock = Generating & { type: 'generating' };

/** The ordered render-block union the server returns; appended verbatim. */
export type Block =
  | BubbleBlock
  | UserBubbleBlock
  | ChipRowBlock
  | StepperCardBlock
  | CalendarBlock
  | FileCardBlock
  | NoteListCardBlock
  | DataCardBlock
  | ErrorBubbleBlock
  | TicketConfirmationBlock
  | GeneratingBlock;

export type BlockType = Block['type'];

/** Every block `type` discriminator in the frozen contract (exactly 11). */
export const BLOCK_TYPES = [
  'bubble',
  'user_bubble',
  'chip_row',
  'stepper_card',
  'calendar',
  'file_card',
  'note_list_card',
  'data_card',
  'error_bubble',
  'ticket_confirmation',
  'generating',
] as const satisfies readonly BlockType[];

/** `ChatResponse` with the block array narrowed to the discriminated union. */
export type TypedChatResponse = Omit<ChatResponse, 'blocks'> & { blocks: Block[] };
