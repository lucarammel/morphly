# Non-goals

Deliberately absent, each with the tipping point that would justify adding it. A missing feature here is a
decision, not a gap — and every line names what would change the decision.

| Absent | Tipping point |
|---|---|
| DAG, automatic scheduling | `Pipeline` is an ordered list. Add this when manual ordering becomes *wrong*, not when it becomes long. |
| Parallelism | When two independent steps dominate measured runtime. |
| Built-in snapshots / rollback / diff | `deepcopy` covers the cases — see [Recipes](recipes.md#snapshot-and-restore). Add this if memory becomes the limiting factor. |
| Loading / writing to disk, formats | Out of scope: `morph` orchestrates, the caller loads and writes. |
| Declarative scope filters (`get_filters`) | Filtering belongs to loading (build a reduced `Store`) or to the module. `Annotated[list[X], Where(...)]` is the extension point if it's ever worth it. |
| YAML/TOML loading of `Config` | `PayrollPolicy.model_validate(tomllib.loads(path.read_text()))` fits on one line, no dependency needed in the core. |
| Declarative pipeline (workflow file) | The caller maps its step names to its functions; that's 5 lines on their side, and only they know their names. |
| Plugin registry / entry points | When modules live in third-party packages. |
| Branching, loops | A plain Python function calling two `Pipeline`s does the job — see [Recipes](recipes.md#branch-loop-or-run-pipelines-in-sequence). |
| Reading one entity by name in a signature | Two injectable shapes keep the contract readable. A module that needs one object reads the list and indexes it. |
