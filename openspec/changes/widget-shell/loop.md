# loop.md — widget-shell

Worktree lead loop state. Source of truth for resume. Rule: if it isn't here,
it didn't happen.

- Change ID / branch: widget-shell
- Worktree: /home/choice/projects/customer-support/widget-shell
- Base: main @ cfb22a1 (contracts-foundation merged)
- testCommand: `npm --prefix widget test`
- doneCondition: manifest.yaml (all block types render from fixtures + match
  prototype; both entry seeds; interaction contracts; shell behaviors; one POST
  per action; accessToken never logged/persisted). Plus Gate-1 amendments:
  WebMCP registration (item 6) and agent-driven E2E (item 7).

## Contract resolutions (frozen schema is authoritative; NOT reinterpretation)
- [CONFIRM #1 — generated TS artifact] RESOLVED: `wireTypes.ts` is generated
  from `app/contracts/schema/chat_wire.schema.json` (the JSON-schema artifact),
  not hand-mirrored. Directed by assignment ("generate TS types from the
  checked-in schema").
- [CONFIRM #2 — remote-config path] RESOLVED: config folded into first
  `/api/chat` response as `config_slice` (present in `ChatResponse`). Single
  network surface: `POST /api/chat`. No separate remote-config GET.
- Prose vs schema divergences (schema wins, per "wireTypes.ts subordinate to the
  contract" + frozen/never-edit): underscore type discriminators; split
  `bubble`/`user_bubble`; `generating` is a first-class block; chips carry
  `{label, action:{kind,payload}}` (typed ChipAction set) rather than a bare
  `actionToken`. Recorded for the final report as [CONFIRM]-resolved, not
  escalations.

## Tasks
| # | Task | Status |
|---|------|--------|
| T1 | Scaffold Vite+React+TS under widget/ | done (npm install ok; typecheck+smoke green) |
| T2 | Generate wire types from frozen schema | done (gen:types → wireTypes.generated.ts; Block union; coverage test green) |
| T3 | Design tokens + theming | done (FinX tokens light+dark; useTheme; no-web-font grep test green) |
| T4 | Bootstrap from URL params | pending |
| T5 | Mock server + fixtures | pending |
| T6 | chatClient + conversation state | pending |
| T7 | Render-block component set | pending |
| T8 | Interaction contracts | pending |
| T9 | Shell + entry surfaces | pending |
| T10 | WebMCP registration | pending |
| T11 | App assembly + mock entrypoint | pending |
| T12 | Agent-driven E2E | pending |

Current task: T4 (about to start) — bootstrap from URL params

## Verifier rounds
(none yet)

## Behavior harness runs
(none yet)

## Open questions / escalations
(none)
