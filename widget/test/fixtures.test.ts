import { describe, it, expect, beforeAll } from 'vitest';
import Ajv, { type ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ALL_BLOCK_FIXTURES, EXTRA_FIXTURES } from '../mock/fixtures/blocks';
import { handleChat, resetMock } from '../mock/server';
import type { SessionContext } from '../src/api/wireTypes';

const schema = JSON.parse(
  readFileSync(resolve(__dirname, '../../app/contracts/schema/chat_wire.schema.json'), 'utf8'),
);

// Map each block `type` discriminator to its $def in the frozen schema.
const DEF_BY_TYPE: Record<string, string> = {
  bubble: 'Bubble',
  user_bubble: 'UserBubble',
  chip_row: 'ChipRow',
  stepper_card: 'StepperCard',
  calendar: 'Calendar',
  file_card: 'FileCard',
  note_list_card: 'NoteListCard',
  data_card: 'DataCard',
  error_bubble: 'ErrorBubble',
  ticket_confirmation: 'TicketConfirmation',
  generating: 'Generating',
};

let ajv: Ajv;
let responseValidator: ValidateFunction;

beforeAll(() => {
  ajv = new Ajv({ strict: false, allErrors: true });
  addFormats(ajv);
  ajv.addSchema(schema, 'wire');
  responseValidator = ajv.getSchema('wire#/$defs/ChatResponse')!;
});

const supportSession: SessionContext = {
  user_id: 'X008593',
  session_id: 's',
  access_token: 't',
  platform: 'web',
  page: 'support',
  entry_surface: 'support',
  is_dark_theme: false,
};

describe('block fixtures validate against the frozen schema', () => {
  it.each(Object.entries(ALL_BLOCK_FIXTURES))('%s matches its $def', (type, fixture) => {
    const validate = ajv.getSchema(`wire#/$defs/${DEF_BY_TYPE[type]}`)!;
    const ok = validate(fixture);
    if (!ok) throw new Error(`${type} invalid: ${ajv.errorsText(validate.errors)}`);
    expect(ok).toBe(true);
  });

  it('extra fixture variants also validate', () => {
    const checks: Array<[string, unknown]> = [
      ['Bubble', EXTRA_FIXTURES.complianceBubble],
      ['FileCard', EXTRA_FIXTURES.cmlFileCard],
      ['DataCard', EXTRA_FIXTURES.holdingCard],
      ['ErrorBubble', EXTRA_FIXTURES.timeoutErrorBubble],
    ];
    for (const [def, obj] of checks) {
      const validate = ajv.getSchema(`wire#/$defs/${def}`)!;
      const ok = validate(obj);
      if (!ok) throw new Error(`${def} invalid: ${ajv.errorsText(validate.errors)}`);
      expect(ok).toBe(true);
    }
  });
});

describe('mock turn responses validate against ChatResponse', () => {
  it('seed response carries config_slice on turn 0 and validates', () => {
    resetMock();
    const seed = handleChat({ session: supportSession, turn_number: 0 });
    expect(seed.config_slice).toBeTruthy();
    const ok = responseValidator(seed);
    if (!ok) throw new Error(ajv.errorsText(responseValidator.errors));
    expect(ok).toBe(true);
  });

  it('a subsequent turn has NO config_slice and validates', () => {
    resetMock();
    const seed = handleChat({ session: supportSession, turn_number: 0 });
    const next = handleChat({
      session: supportSession,
      thread_id: seed.thread_id,
      turn_number: 1,
      message: 'Get my P&L',
    });
    expect(next.config_slice ?? null).toBeNull();
    const ok = responseValidator(next);
    if (!ok) throw new Error(ajv.errorsText(responseValidator.errors));
    expect(ok).toBe(true);
  });
});
