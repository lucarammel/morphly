# Validation

Three barriers, from earliest to latest.

| When | What's checked | Exception |
|---|---|---|
| `@module` (import) | Every parameter annotated, supported annotation, return annotated, `Patch`/`Delete` parameterized | `TypeError` |
| `check` (start of `run`) | Every type read or touched is provided by the initial `Store` or by an upstream step | `LookupError` |
| per step, before applying | Output contract honored; `Patch`/`Delete` targets present and unambiguous; `Patch` fields exist | `TypeError` / `KeyError` / `ValueError` |
| on apply | pydantic validation of every object and every written field | `ValidationError` |

`check` simulates the pipeline on **types**: it starts from `store.types()` and adds, after each step, the
types it produces. A module reading `Trade` when no upstream step produces it and the `Store` doesn't
contain it fails in a millisecond, not after three hours of computation.

## Application semantics

- A step's outputs are **collected, validated, then applied**. A step never applies halfway.
- Application order = return order. `put` then `Delete` on the same object leaves it deleted.
- `put` on an existing `(type, name)` **replaces** the object. Partial updates go through `Patch`.
- The `Store` is mutated in place. For a non-destructive run: `pipeline.run(copy.deepcopy(store))`.
