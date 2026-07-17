import { describe, it, expect } from 'vitest';
import { BLOCK_TYPES, type Block, type BlockType } from '../src/api/wireTypes';

// The generated types come straight from the frozen schema; this guards that
// the discriminated `Block` union exposes exactly the 11 contract block types
// and nothing drifts.
describe('wire block union', () => {
  it('covers exactly the 11 frozen block discriminators', () => {
    expect([...BLOCK_TYPES].sort()).toEqual(
      [
        'bubble',
        'calendar',
        'chip_row',
        'data_card',
        'error_bubble',
        'file_card',
        'generating',
        'note_list_card',
        'stepper_card',
        'ticket_confirmation',
        'user_bubble',
      ].sort(),
    );
  });

  it('BLOCK_TYPES is assignable to BlockType and vice versa (compile-time)', () => {
    // If a block type is added/removed in the union but not in BLOCK_TYPES (or
    // vice versa) this stops compiling via `satisfies` in the source; here we
    // assert the runtime list length matches the 11-member union.
    const seen: Record<BlockType, true> = {
      bubble: true,
      user_bubble: true,
      chip_row: true,
      stepper_card: true,
      calendar: true,
      file_card: true,
      note_list_card: true,
      data_card: true,
      error_bubble: true,
      ticket_confirmation: true,
      generating: true,
    };
    expect(Object.keys(seen)).toHaveLength(BLOCK_TYPES.length);
  });

  it('narrows on the type discriminant', () => {
    const block: Block = { type: 'bubble', text: 'hi' };
    if (block.type === 'bubble') {
      expect(block.text).toBe('hi');
    }
  });
});
