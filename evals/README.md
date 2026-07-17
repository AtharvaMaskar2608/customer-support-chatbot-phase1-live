# Choice Jini — evaluation harness (`evals/`)

The machine-runnable eval layer the spec prescribes (§7.4 / §7.6). It turns the
human QA workbook (`docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx`) into
scenario-based DeepEval goldens, drives the real Jini app through a
`ConversationSimulator`, scores it with a metric set at proposed thresholds, and
gates the build on the blocker-severity cases.

## Layout

| File | Purpose |
|---|---|
| `goldens/phase1_kb.py` | A-E `ConversationalGolden`s (RAG-only bot) |
| `goldens/phase2_api.py` | F-M `ConversationalGolden`s (RAG + API bot) |
| `goldens/__init__.py` | dataset assembly + category / severity / blocker tagging |
| `simulator.py` | async `model_callback` returning rich `Turn`s; greeting seed |
| `metrics.py` | metric factories + `chatbot_role`, `relevant_topics`, safety GEval |
| `thresholds.yaml` | the proposed thresholds — **single source, decisions for review** |
| `judge.py` | `claude-opus-4-8` `DeepEvalBaseLLM` judge/simulator wrapper (+ OpenAI alt) |
| `synthetic.py` | optional `Synthesizer` seeding of RAG goldens from `qa_chunks` |
| `test_multiturn.py` | `deepeval test run` conversational target; blocker gating |
| `test_rag_singleturn.py` | single-turn RAG triad target |
| `test_goldens.py`, `test_callback.py` | offline structural tests (no LLM calls) |
| `conftest.py` | dataset + judge fixtures, `@deepeval.log_hyperparameters` |

## Running

### Offline structural checks (no API key, no app, no network — CI-safe)

Validate the goldens, tags, thresholds, and callback plumbing against fakes:

```bash
uv run pytest evals/ -k "goldens or callback"
```

This is the Wave-1 gate. It never makes a live LLM call.

### Live evaluation (Wave 2 — requires the assembled app + API keys)

The `deepeval test run` targets are **guarded**: they skip unless `EVAL_LIVE=1`
is set. Once the orchestrator + RAG + flows + ticketing are merged and a Jini
app is reachable, run:

```bash
EVAL_LIVE=1 uv run deepeval test run \
  evals/test_multiturn.py evals/test_rag_singleturn.py
```

Blocker-severity goldens (see below) fail the build on regression.

## Judge model (decision for review)

The judge + simulated-user model is **`claude-opus-4-8`** (`judge.py`),
deliberately *stronger than and independent of* the `claude-sonnet-5`
system-under-test — a judge that shares the SUT's model exhibits
self-preference bias. It reuses the existing `ANTHROPIC_API_KEY`; no new secret.

Documented alternative: DeepEval's native OpenAI judge (`gpt-4.1`) via the
existing `OPENAI_API_KEY`. Select it with `JINI_JUDGE_PROVIDER=openai`. This is a
**decision for owner review**, not silently settled.

## Thresholds (decisions for review)

All thresholds live in `thresholds.yaml` (0.7-0.9, tutorial defaults as the
start; 0.9-strict for the safety blocker). They are proposals — tune after a
review pass. No threshold is hardcoded at a call site.

## Workbook count reconciliation (41 / 47, not 36 / 46)

The workbook's `00_README` sheet claims **36 / 46** cases. Parsing the actual
sheets gives different totals, and the goldens are authored against the **true**
counts:

| Sheet | README claim | Actual (parsed) | Categories |
|---|---|---|---|
| `Phase1_KB_Bot` | 36 | **41** | A8, B5, C8, D8, E12 |
| `Phase2_TopN_Bot` | 46 | **47** | F7, G6, H8, I5, J4, K7, L7, M3 |

The discrepancy is recorded here so nobody re-derives the wrong count from the
README sheet.

### Blocker cases (build-gating)

Verified against the workbook's `Severity` column (`Blocker` rows only):

- **Phase 1 (10):** B3, C1, C2, C3, C5, C6, C7, C8, D3, D4
- **Phase 2 (7):** F7, G1, G5, H8, I1, I2, I3

Each becomes a `severity="blocker"` golden with a strict threshold; a single
blocker failure holds the build, mirroring the workbook's launch-severity model.

## Anti-pattern: never replay production transcripts as benchmarks

The spec flags this twice (`chatbot_eval/1` Caution, `chatbot_eval/3` Historical
Replay). Historical conversations were shaped by the *current* system — they
cannot stress new prompts, catch regressions in unseen scenarios, or surface
edge cases users have not hit yet.

**Rule:** `evals/goldens/` contains only forward-looking, scenario-based
`ConversationalGolden`s. Production failures re-enter as *newly authored*
scenarios, never as verbatim transcript replays. `test_goldens.py` enforces this
(every golden must be scenario-based, with no seeded `turns` transcript).
