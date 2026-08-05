# Modules and pipelines

A module is a function decorated with `@module`.

```python
@module
def bidding(plants: list[Plant], params: BidParams) -> list[Order]:
    return [Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost * params.margin) for p in plants]
```

## Injection rules (parameters)

| Annotation | Receives | Error |
|---|---|---|
| `list[X]`, `X: Entity` | `store.all(X)` — a list, possibly empty | `TypeError` if `X` is not an `Entity` |
| `X`, `X: Config` | the step's config, else `store.one(X)` | `LookupError` if missing / ambiguous |
| missing | — | `TypeError` at declaration |
| other (`dict`, `str`, `Store`, …) | — | `TypeError` at declaration |

Injected values are **deep-copied** by default: a module can't corrupt the state read by another one.
`Pipeline.run(copy_inputs=False)` disables the copy when volume demands it — the isolation guarantee then
disappears, and that's a conscious choice, not a default.

## Output rules (return value)

The return annotation is **required** and forms the output contract.

| Return | Effect |
|---|---|
| `None` | No change. Read-only module (export, monitoring, metrics). |
| an `Entity` / a `Config` | Upsert. |
| an iterable of `Entity` / `Config` / `Patch` / `Delete` | Applied in order. |

```python
-> list[Order]                            # creates / replaces Order instances
-> list[Patch[MarketArea]]                # updates a few fields
-> list[Delete[Order]]                    # deletes
-> list[Order | Patch[MarketArea]]        # several types, several operations
-> None                                   # touches nothing
```

Producing an undeclared type is a `TypeError`. The contract distinguishes:

- **produced** (`-> list[Order]`): the type may not exist yet, it will be created;
- **touched** (`Patch[X]`, `Delete[X]`): the type must already exist.

This is what lets `check` reason about the chaining — see [Validation](validation.md).

## `Step` — per-step configuration

A pipeline can run **the same module twice with different parameters** (day-ahead clearing then intraday,
two zones, two horizons). Config therefore lives at the step level:

```python
Pipeline(
    Step(clearing, ClearingParams(mode="DA"), name="clearing_da"),
    Step(clearing, ClearingParams(mode="ID"), name="clearing_id"),
    settlement,                       # bare module: config read from the Store
)
```

- `Step(module, *configs, name=None)` — `name` defaults to the function's name, suffixed on collision.
- Resolving a `Config`: the step's configs first, then `store.one(...)`.
- A bare module passed to `Pipeline` is equivalent to `Step(module)`.

## `Pipeline`

| Method | Effect |
|---|---|
| `run(store, *, copy_inputs=True, on_step=None)` | `check`, then runs the steps in order. Returns the mutated `store`. |
| `check(store)` | Validates the chaining without running anything. |
| `explain()` | Renders the reads / creates / modifies graph, one line per step. |

`on_step(step, store)` is called after each step: logs, metrics, snapshots, writing outputs. A single
hook covers every observability need.
