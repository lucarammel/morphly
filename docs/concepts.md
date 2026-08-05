# Concepts

## `Entity`

A shared business object, identified by `name` **within its type lineage**.

```python
class Plant(Entity):
    pmax: float
    cost: float
```

- `Entity` inherits from `pydantic.BaseModel`, enforces `name: str` (frozen), and enables
  `validate_assignment=True` (every field write is validated) and `arbitrary_types_allowed=True` (fields
  carrying non-pydantic objects: timeseries, matrices, solver handles).
- Identity is the `(type, name)` pair.
- Subclasses are a first-class case: reading `list[Plant]` also returns `ThermalPlant` instances.

## `Config`

A **singleton** input: module parameters, global settings, context.

```python
class BidParams(Config):
    margin: float = 1.0
```

No `name`. Resolved by type, either on the step or in the `Store` — see
[Step](modules-and-pipelines.md#step-per-step-configuration).

## `Store`

The shared state. Buckets by concrete type, read by type (subclasses included).

| Method | Effect |
|---|---|
| `Store(*items)` | Builds and fills. |
| `put(*items)` | Upsert. `Entity` → key `(type, name)`. `Config` → key `type`. |
| `all(cls)` | Every instance of `cls` and its subclasses. |
| `one(cls)` | The single instance of `Config` `cls`. `LookupError` if 0 or > 1. |
| `find(cls, name)` | The object named `name`: exact type first, then the lineage of `cls`. `KeyError` if missing or ambiguous. |
| `drop(target)` | Removes the targeted object. |
| `patch(target, fields)` | Writes the targeted fields onto the object in the `Store`. |
| `types()` | Types currently present. |

**Target resolution.** A module often works on an enriched *view* (`MarketAreaMC(MarketArea)`), and returns
`Patch(mc_area, price=...)`. The target is resolved against the type **declared in the return annotation**
(`Patch[MarketArea]`), not the view's own class: the view can therefore be a sibling of the stored type.
`Store.find` looks in the exact type's bucket first, then the lineage; ambiguity (two objects with the same
`name` in two sibling types) is an explicit error, not an arbitrary choice.

The `Store` is a plain Python object: `copy.deepcopy(store)` is a snapshot, `pickle` persists it.

## `Patch[E]` and `Delete[E]`

```python
Patch(order, accepted_power=ts, spread=0.3)   # partial update
Delete(order)                                 # deletion
```

- `Patch` only writes the fields it's given — the normal output of a module that computes a few
  attributes on existing objects without touching the rest (or references to it).
- Returning a full `Entity` means creation or **full replacement**.
- The type parameter is **required in the return annotation**: `list[Patch[Order]]`. That's how the module
  declares it touches `Order`. A bare `list[Patch]` is a declaration error.

## `view` (sugar)

```python
mc_order = view(OrderMC, order, times=times, timestep=timestep)
```

Builds an enriched view from a shared entity: shallow-copies the source's fields, adds the extras, then
validates against the target class. Replaces the hand-written
`model_validate({**shallow_dump(obj), ...})` in every module.
