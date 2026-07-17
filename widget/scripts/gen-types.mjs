// Generate widget/src/api/wireTypes.generated.ts from the FROZEN contract
// app/contracts/schema/chat_wire.schema.json. The schema is the single source
// of truth for the wire block union; this script never edits it. Run via
// `npm run gen:types`. The generated file is committed so the build/typecheck
// does not depend on codegen at build time.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { compile } from 'json-schema-to-typescript';

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, '../../app/contracts/schema/chat_wire.schema.json');
const outPath = resolve(here, '../src/api/wireTypes.generated.ts');

const schema = JSON.parse(await readFile(schemaPath, 'utf8'));

const banner = `/**
 * GENERATED — do not edit by hand.
 * Source: app/contracts/schema/chat_wire.schema.json (frozen contract).
 * Regenerate: npm run gen:types
 */
`;

const ts = await compile(schema, 'WireSchemaRoot', {
  additionalProperties: false,
  bannerComment: '',
  style: { singleQuote: true, semi: true },
});

await writeFile(outPath, banner + ts, 'utf8');
console.log(`wrote ${outPath}`);
