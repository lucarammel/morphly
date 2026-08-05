# Non-goals

Deliberately absent, with the tipping point that would justify adding them:

| Absent | Tipping point |
|---|---|
| DAG, automatic scheduling | `Pipeline` is an ordered list. Add this when manual ordering becomes *wrong*, not when it becomes long. |
| Parallelism | When two independent steps dominate measured runtime. |
| Built-in snapshots / rollback / diff | `deepcopy` covers the cases. Add this if memory becomes the limiting factor. |
| Loading / writing to disk, formats | Out of scope: `morph` orchestrates, the caller loads and writes. |
| Declarative scope filters (`get_filters`) | Filtering belongs to loading (build a reduced `Store`) or to the module. `Annotated[list[X], Where(...)]` is the extension point if it's ever worth it. |
| YAML/TOML loading of `Config` | `Params.model_validate(yaml.safe_load(p.read_text()))` fits on one line, no dependency needed in the core. |
| Declarative pipeline (workflow file) | The caller maps its step names to its functions; that's 5 lines on their side, and only they know their names. |
| Plugin registry / entry points | When modules live in third-party packages. |
| Branching, loops | A plain Python function calling two `Pipeline`s does the job. |
