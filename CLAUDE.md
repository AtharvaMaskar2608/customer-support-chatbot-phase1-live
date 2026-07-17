# Operating model: autonomous loop-engineered pipeline

This repo runs on autonomous agents with exactly two human gates:
**Gate 1 — proposal review** and **Gate 2 — merge review**. Everything
between the gates is machine loops with verifiable exit conditions.
Never ask the human for a decision the pipeline already covers; escalate
only at the gates or through the escalation rules below.

Core principle: **persistent identity for coordinators, disposable fresh
contexts for judges.** Leads and worktree owners keep memory across the
change; verifiers are spawned from scratch every time, on purpose.

## Roles

- **Team lead (orchestrator):** persistent. Creates and assigns
  worktrees, sequences waves, owns escalations to the human.
- **Worktree lead:** one per approved change, persistent for the life of
  that change. Owns its worktree, its branch, its commits.
- **Implementer/test subagents:** spawned by a worktree lead for tasks
  inside its worktree.
- **Verifiers:** disposable, fresh-context subagents. Never reused,
  never teammates. See Verification protocol.
- **Scribe:** orchestrator-level agent that owns Linear hygiene
  (create/update/close issues, status transitions, progress comments).
  No other agent writes to Linear.

## Pipeline

1. **Propose (parallel).** Specs are generated via OpenSpec before any
   implementation. One proposer per issue; proposers run in parallel
   (proposal writing is read-only against the codebase; each writes only
   its own `openspec/changes/<change-id>/`). Every proposal includes the
   manifest below.
2. **Reconcile (barrier).** After all proposals exist: compute file
   overlaps from manifests (set intersection), check contract collisions
   semantically, revise conflicting proposals with the other proposal's
   contract in context. Loop until a pass finds zero new conflicts, then
   produce the parallelization plan.
3. **Gate 1 (human):** proposals + parallelization plan reviewed as one
   batch.
4. **Wave 0:** land contract changes (shared types/interfaces/API
   schemas) on main, sequentially, before any fan-out.
5. **Fan-out:** team lead creates one worktree per approved change and
   assigns a worktree lead. Waves run per the plan.
6. **Inner loop (per worktree):** implement → fresh verifier panel →
   fix → repeat. Exit: a fresh panel finds zero divergences. Bound:
   3 rounds, then escalate to the team lead.
7. **Ship:** panel clean → rebase onto latest main → full behavior
   harness green on the rebased head → PR with structured recap
   (use /ship).
8. **Gate 2 (human):** PR review and merge.
9. **Post-merge:** team lead runs the behavior harness on main (red →
   stop the line); green → all still-open worktrees rebase and re-run
   the harness; scribe closes the ticket; deploy via /land-and-deploy
   when instructed.

## Proposal shaping (design for autonomy)

- Decompose work into vertical slices that own their files end-to-end;
  avoid layer-based slices ("all API changes") that force overlap.
- If two proposals need the same types/schemas/interfaces, extract that
  surface into a separate minimal contract-change that lands on main
  first (Wave 0), making the remaining changes disjoint. Prefer
  re-slicing over sequencing.
- Hot files (route registries, root config, lockfiles, dependency
  manifests, migrations): proposals must prefer additive patterns over
  editing them; unavoidable edits go in the contract wave or to a single
  explicitly assigned owner.
- Parallelizability is a tiebreaker, never the objective: between
  equally sound decompositions, pick the one with fewer overlaps and
  dependencies. Never fragment a coherent change just to parallelize it.

## Proposal manifest (required, machine-readable)

Every proposal declares:

- `filesTouched[]` — every file/directory it will create or modify
- `contracts[]` — every type/interface/endpoint it defines or consumes,
  with full structure (request/response shape per function and endpoint)
- `dependsOn[]` — other change IDs whose contracts it needs
- `doneCondition` — an executable command that exits 0 when the change
  is complete. Never prose: a loop cannot halt on a sentence.
- `testCommand` — the command that proves it
- `visualPlan` (optional) — URL of the visual plan, when one was
  generated for this change. Scribe and committers read the link from
  here; if the field is absent, they omit it — never invent a link.

## Parallelization plan (required, after reconcile)

From the manifests, produce a wave plan:

- **Wave 0:** contract changes → main, sequential.
- **Wave 1:** all mutually disjoint changes, fan out in parallel.
- **Wave N:** changes gated on earlier waves' contracts.

Include the merge/rebase order. A file overlap within a wave is a plan
error: re-slice the proposals or move a change to a later wave.

## Worktree rules

- Only the team lead creates worktrees. One worktree per approved
  change: change ID = branch name = worktree directory = Linear ticket.
- A worktree lead writes only inside its assigned worktree. Nothing
  outside it, ever.
- Isolation is per-worktree, not per-subagent: subagents inside one
  worktree must not edit the same file concurrently — the worktree lead
  sequences overlapping edits.
- Max 4 concurrent worktrees; the plan queues the rest.
- Worktrees are removed after merge; the team lead owns cleanup.

## Verification protocol (fresh-context panels)

- Verifiers are spawned from scratch with only two inputs: the proposal
  artifacts (`openspec/changes/<change-id>/`) and the branch diff. Never
  give them the implementer's conversation or reasoning.
- Prompt to refute, not confirm: "list every divergence between what was
  specified and what was built" — an empty list only after checking
  every task. Never "verify this is correct."
- Panels have 3 verifiers with distinct lenses: (a) spec compliance
  task-by-task, (b) edge cases and failure paths, (c) contract/API
  surface vs. what landed on main. Majority vote settles disputed
  findings.
- Fresh every round: after fixes, spawn a new panel. Never re-ask a
  verifier that has already seen the code.
- Verifiers cannot renegotiate the spec. Divergence from spec → the
  implementer fixes. Suspected error in the spec → escalate to the team
  lead → human. The proposal approved at Gate 1 is the contract.

## Two harnesses (spec and behavior)

Every change must pass both; they answer different questions and one
never substitutes for the other.

1. **Spec harness** (per-change, in the worktree, pre-merge): verifier
   panels + doneCondition + testCommand. Answers: did we build what
   was approved at Gate 1?
2. **Behavior harness** (system-level, on integrated code): the full
   unit + integration test suite, plus the eval suite (DeepEval) and
   /qa where the change touches chat behavior or UI. Answers: does the
   product behave correctly as a whole?

Behavior harness runs at two moments:

- **Pre-Gate 2:** the worktree lead rebases onto latest main and runs
  the FULL suite — not just its own testCommand. A PR is not ready for
  human review until green on the rebased head.
- **Post-merge:** the team lead runs the full suite on main after
  every merge. Main red → stop the line: no further merges or fan-out
  until main is green; fixing main is the top priority. Main green →
  team lead tells all open worktree leads to rebase; each re-runs the
  behavior harness on its rebased head.

Test authorship rule: tests are written from the proposal, not from
the implementation. A test that asserts what the code currently does
is not evidence; a test that asserts what the spec promised is.

## Commits, tickets, escalation

- Commit messages are written by the agent that made the change, in
  context — never delegated to a scribe. Small, per-task commits.
  Subject: what changed and which proposal task it completes. Body: a
  good-enough summary a reviewer can understand without the diff, plus
  the manifest's visualPlan link when present.
- The PR description carries the fuller recap: change summary, tasks
  completed, verifier rounds, and the visualPlan link when present.
- The scribe owns all Linear writes: issue created at Gate 1 approval,
  In Progress at fan-out, In Review at PR, Done at merge. Every issue
  and its In Review / Done comments include a good-enough summary and
  the visualPlan link when present.
- Linear structure: project = proposal batch, issue = change,
  sub-issue = proposal task (from tasks.md), blocked-by relations from
  dependsOn[], wave labels from the plan. Sub-issue states sync from
  loop.md only. Full protocol in the scribe agent definition.
- Escalate to the human only when: a verify loop fails to converge in
  3 rounds, a spec error is suspected, a merge conflict can't be
  resolved by rebase, or scope changes beyond the approved proposal.

## Loop state & instrumentation

- Loop memory lives in files, not context. Every worktree lead
  maintains `openspec/changes/<change-id>/loop.md`: tasks completed,
  current task, verifier rounds, findings per round, open questions —
  updated after every task and every round. If it isn't in loop.md, it
  didn't happen; a restarted agent must be able to resume from that
  file alone.
- Verification is never self-review in the same context ("checker
  theater"): exit conditions are checked by executable commands and
  fresh-context verifiers, never by the agent that did the work.
- On completion, loop.md records per-change metrics: verifier rounds
  used, findings per round, escalations. These feed /retro — watch
  intervention rate and rework ratio to decide where autonomy can
  expand next.

## Agent definitions

The roles above are spawnable types in `.claude/agents/`: `proposer`,
`worktree-lead`, `spec-verifier`, `scribe`. Spawn those types rather
than improvising role prompts inline.
