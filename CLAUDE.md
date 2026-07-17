## Parallel workflow rules
- Specs are generated via OpenSpec before any implementation.
- Before proposing parallel execution, list every file/directory each task will touch.
- Tasks with overlapping files, or that depend on an undefined contract, must run sequentially or wait for the contract to land in main.
- Shared types/interfaces/API schemas are committed to main before fan-out.
- No task may modify lockfiles, migrations, or root config unless explicitly assigned.
- Each task must state its "done" condition and test command.

- Mention Contracts and API structure for each function and endpoint. 

- After making all the proposals revisit the other existing proposals for any potential merge conflicts and surface it. Be open to updating your proposal in order to avoid the conflicts.

- Based on all the propsals create a parallelization plan. 

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore