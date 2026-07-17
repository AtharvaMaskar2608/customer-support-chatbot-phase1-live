# Tasks — eval-harness

Authored from proposal.md (Wave 1: authoring + unit level; no live E2E runs).
Each task is one commit. Structural checks run offline against fakes.

## T1 — Package scaffold + reconciliation + thresholds
- [ ] `evals/__init__.py` — package init; opt out of DeepEval telemetry so CI is hermetic.
- [ ] `evals/thresholds.yaml` — single source of proposed thresholds (0.7-0.9),
  marked DECISIONS FOR REVIEW.
- [ ] `evals/README.md` — how to run; the 41/47-vs-36/46 workbook reconciliation;
  the no-historical-replay anti-pattern rule.

## T2 — Judge / simulator model wrapper
- [ ] `evals/judge.py` — `JiniJudgeLLM(DeepEvalBaseLLM)` wrapping `claude-opus-4-8`
  via the anthropic SDK (lazy client; no key/network at import). `build_judge()`
  selects Claude (default) or the OpenAI `gpt-4.1` alternative via env.

## T3 — Goldens (>=20 ConversationalGoldens, A-M, blocker-tagged)
- [ ] `evals/goldens/phase1_kb.py` — A-E goldens grounded in the 41 Phase-1 cases.
- [ ] `evals/goldens/phase2_api.py` — F-M goldens grounded in the 47 Phase-2 cases.
- [ ] `evals/goldens/__init__.py` — dataset assembly; category/severity/case_id/
  blocker tagging in `additional_metadata`; `BLOCKER_CASE_IDS` (the 17);
  `blocker_goldens()` / `ALL_GOLDENS` / `DATASET`.

## T4 — ConversationSimulator plumbing
- [ ] `evals/simulator.py` — async `model_callback(input, turns, thread_id) -> Turn`
  returning content + retrieval_context + tools_called; `drive_jini_chat`
  (pluggable driver so the mapping is testable offline); `render_blocks_to_text`;
  `greeting_seed_turn`; `build_simulator(judge)`.

## T5 — Metric set + thresholds wiring
- [ ] `evals/metrics.py` — `conversational_metrics()`, `rag_singleturn_metrics()`,
  `blocker_safety_metric()` factories reading `thresholds.yaml`; `CHATBOT_ROLE`,
  `RELEVANT_TOPICS`, `AVAILABLE_TOOLS` (from frozen `app.contracts.tools.TOOLS`);
  the "never gives investment advice" `ConversationalGEval`.

## T6 — Optional synthetic seeding
- [ ] `evals/synthetic.py` — optional `Synthesizer` seeding of single-turn RAG
  goldens from `qa_chunks` contexts (guarded; not run in CI).

## T7 — deepeval test-run targets (Wave-2 live; guarded offline)
- [ ] `evals/conftest.py` — dataset + judge fixtures; `@deepeval.log_hyperparameters`.
- [ ] `evals/test_multiturn.py` — conversational target; blocker-severity goldens
  gate the build; module-level skip unless `EVAL_LIVE=1`.
- [ ] `evals/test_rag_singleturn.py` — single-turn RAG triad target; same guard.

## T8 — Offline structural tests + anti-pattern guard
- [ ] `evals/test_goldens.py` — >=20 goldens, A-M coverage, blocker tags == the 17,
  thresholds.yaml completeness, the no-raw-transcript guard.
- [ ] `evals/test_callback.py` — model_callback returns a rich Turn (content +
  retrieval_context + tools_called) via a fake driver; greeting-seed shape.

## T9 — Structural gate
- [ ] `pytest evals/ -k "goldens or callback"` green offline; fix until clean.
- [ ] Fresh verifier panel (3 lenses); fix; ship.
