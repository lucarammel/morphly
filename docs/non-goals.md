# Non-goals

Deliberately absent, each with the tipping point that would justify adding it. A missing feature here is a
decision, not a gap — and every line names what would change the decision.

| Absent | Tipping point |
|---|---|
| DAG, automatic scheduling | `Workflow` is an ordered list. Add this when manual ordering becomes *wrong*, not when it becomes long. |
| Parallelism | When two independent steps dominate measured runtime. |
| Snapshot format, diff between runs | `deepcopy` and `pickle` cover the cases — see [Recipes](recipes.md#snapshot-and-restore). Rollback *was* on this list; `run(atomic=True)` now covers it, because the tipping point turned out not to be memory but a silent default: only the caller who already knew to copy the store was safe. |
| Loading / writing to disk, formats | Out of scope: `morphly` orchestrates, the caller loads and writes. |
| Declarative scope filters (`get_filters`) | Filtering belongs to loading (build a reduced `Store`) or to the module. `Annotated[list[X], Where(...)]` is the extension point if it's ever worth it. |
| YAML/TOML loading of `Config` | `PayrollPolicy.model_validate(tomllib.loads(path.read_text()))` fits on one line, no dependency needed in the core. |
| Declarative workflow definitions (from a file) | The caller maps its step names to its functions; that's 5 lines on their side, and only they know their names. |
| Plugin registry / entry points | When modules live in third-party packages. |
| Branching, loops | A plain Python function calling two `Workflow`s does the job — see [Recipes](recipes.md#branch-loop-or-run-workflows-in-sequence). |
| Reading one entity by name in a signature | Two injectable shapes keep the contract readable. A module that needs one object reads the list and indexes it. |
