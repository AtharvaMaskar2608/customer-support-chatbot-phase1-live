# loop.md — eval-harness worktree lead state

Resume-from-scratch record. If it isn't here, it didn't happen.

## Contract summary
- Change: `eval-harness` (Wave 1, unit/authoring level).
- Branch/worktree: `eval-harness` @ started from main `cfb22a1`.
- Scope (team-lead directive): AUTHORING + unit level only. >=20 golden
  conversations, metric thresholds (0.7-0.9), judge = `claude-opus-4-8`,
  `ConversationSimulator` plumbing, blocker CI gate. **No live end-to-end runs
  now** (that is Wave 2). Tests validate goldens/config/plumbing OFFLINE — no
  live LLM calls in CI.
- FROZEN, never edit: `app/contracts/**`, `app/finx/*.py`, `app/llm/client.py`,
  `app/config/**`, `app/main.py`, `app/store/migrations/**`, `pyproject.toml`,
  `uv.lock`. All present and verified — no missing frozen surface.
- Env: `uv sync --all-extras` (deepeval already declared in `[dev]` extra).

## Environment facts (verified against installed pkgs)
- deepeval **4.1.1**. yaml 6.0.3, anthropic 0.117.0, openai 2.46.0, httpx 0.28.1
  all importable in the venv (yaml is transitive via deepeval).
- Verified import paths / signatures:
  - `deepeval.dataset.ConversationalGolden(scenario, expected_outcome,
    user_description, additional_metadata=dict, ...)` — no severity/category
    field; tags go in `additional_metadata`.
  - `deepeval.test_case.{Turn, ToolCall, LLMTestCase, ConversationalTestCase}`.
    `Turn(role, content, retrieval_context, tools_called)`;
    `ToolCall(name, description, input_parameters, output)`.
    `ConversationalTestCase(...chatbot_role, tags, metadata...)`.
  - `deepeval.simulator.ConversationSimulator(model_callback, simulator_model,
    ...)` + `.simulate(conversational_goldens, max_user_simulations=10)`.
  - `deepeval.test_case.MultiTurnParams` (for ConversationalGEval
    evaluation_params); `deepeval.test_case.llm_test_case.SingleTurnParams`.
  - Metrics all present in `deepeval.metrics`:
    ConversationCompleteness/TurnRelevancy/KnowledgeRetention/RoleAdherence/
    TopicAdherence(relevant_topics=)/ConversationalGEval/TurnFaithfulness/
    TurnContextual{Relevancy,Precision,Recall}/GoalAccuracy/ToolUse(available_tools=);
    single-turn AnswerRelevancy/Faithfulness/Contextual{Relevancy,Precision,Recall}.
    All accept `threshold=` and `model=` (str | DeepEvalBaseLLM).
  - `deepeval.models.DeepEvalBaseLLM` abstract methods: generate, a_generate,
    load_model, get_model_name.
  - `deepeval.assert_test(test_case, metrics, ...)`; `@deepeval.log_hyperparameters`.
  - Telemetry opt-out env var: `DEEPEVAL_TELEMETRY_OPT_OUT`.
- Chat surface consumed: `POST /api/chat` -> `app.contracts.wire.ChatRequest/
  ChatResponse`; bot text = concatenated `Bubble.text` render blocks; retrieval
  context type `app.contracts.rag.RetrievalContext = list[str]`; tools =
  `app.contracts.tools.TOOLS` (10 frozen tools); `Intent` (16) from router.

## Workbook reconciliation (parsed docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx)
- Sheets: `00_README`, `Phase1_KB_Bot`, `Phase2_TopN_Bot`.
- **Phase1 = 41 cases** (A8, B5, C8, D8, E12). **Phase2 = 47 cases**
  (F7, G6, H8, I5, J4, K7, L7, M3). README's 36/46 claim is wrong — goldens are
  authored against the true 41/47. Recorded in evals/README.md.
- Blocker-severity rows (verified against col G):
  - Phase1 (10): B3, C1, C2, C3, C5, C6, C7, C8, D3, D4.
  - Phase2 (7): F7, G1, G5, H8, I1, I2, I3.
  These are exactly the 17 blockers the proposal maps to build-gating.

## Tasks (see tasks.md)
- [ ] T1 scaffold: package + README (reconciliation + no-replay) + thresholds.yaml
- [ ] T2 judge.py: JiniJudgeLLM(claude-opus-4-8) + selectable OpenAI alt
- [ ] T3 goldens: phase1_kb (A-E) + phase2_api (F-M) + assembly/tagging (>=20)
- [ ] T4 simulator.py: model_callback -> rich Turn, drive_jini_chat, greeting seed
- [ ] T5 metrics.py: metric factories + chatbot_role + relevant_topics + safety GEval
- [ ] T6 synthetic.py: optional Synthesizer seeding from qa_chunks
- [ ] T7 test targets: test_multiturn.py + test_rag_singleturn.py + conftest.py (live-guarded)
- [ ] T8 offline structural tests: test_goldens.py + test_callback.py + anti-pattern guard
- [ ] T9 run structural gate (pytest evals/ -k "goldens or callback"); fix green

## Current task
T1 — scaffolding.

## Verifier rounds
- none yet.

## Open questions
- retrieval_context / tools_called are server-side, NOT on the client wire
  contract. The callback's rich-Turn SHAPE + mapping are authored now; the live
  SOURCE (trace/eval channel) is wired in Wave 2 once the app is assembled.
  Documented in simulator.py + README. Not a spec divergence — Wave-1 is
  plumbing + offline validation per the directive.
