# Validation

Four barriers, from earliest to latest. The point of the ordering is that cheap mistakes are caught before
the expensive work starts.

| When | What's checked | Exception |
|---|---|---|
| `@module` (import) | Every parameter annotated, supported annotation, return annotated, `Patch`/`Delete` parameterized | `TypeError` |
| `check` (start of `run`) | Every entity type read or touched is provided by the initial `Store` or by an upstream step | `LookupError` |
| per step, before applying | Output contract honored; `Patch`/`Delete` targets present and unambiguous; `Patch` fields exist | `TypeError` / `KeyError` / `ValueError` |
| on apply | pydantic validation of every object and every written field | `ValidationError` |

## How `check` works

It replays the workflow on **types**. It starts from `store.types()` and adds, after each step, the types
that step produces:

```text
available = {Employee, Manager, Timesheet, PayrollPolicy}
1. compute_gross  reads Employee ✓ Timesheet ✓, touches Employee ✓
2. add_bonus      reads Manager ✓,              touches Manager ✓
3. withhold       reads Employee ✓                                   → available |= {Payslip}
4. archive        reads Timesheet ✓,            touches Timesheet ✓
5. report         reads Payslip ✓
```

Move `report` to the front and it fails in a millisecond rather than after three hours of computation:

```python
Workflow(report, withhold).check(store)
# LookupError: step 'report' reads Payslip, which is neither in the store
#              nor produced by an upstream step
```

`run` calls `check` first, so you get this for free. You can also call it yourself at startup — it only
reads `store.types()`, so it works on a store built from your schema before any data is loaded.

## What `check` does not catch

Being explicit about the limits is more useful than overselling the guarantee.

**Ordering that is wrong but type-consistent.** Running `add_bonus` before `compute_gross` passes the
check — both types are in the store from the start — and quietly applies a bonus to a `gross` of zero.
`check` reasons about availability, not about freshness. Ordering your steps is still your job.

**Anything about values.** `check` never runs a module. Empty inputs, wrong numbers, an exception in your
own code — none of it is visible to it.

## Application semantics

- A step's outputs are **collected, validated, then applied**. If the eighth operation is invalid, the
  first seven have not been written: a step never applies halfway.
- The **workflow** is not transactional. If step 4 of 5 raises, steps 1–3 are already applied. For a
  non-destructive run, pass a copy: `workflow.run(copy.deepcopy(store))`.
- An exception from a module, or from applying its output, is re-raised **unchanged** with a note naming the
  step, its position and the state of the store. Your `except` clauses keep working.
- Application order is return order. A `put` then a `Delete` on the same object leaves it deleted.
- `put` on an existing `(type, name)` **replaces** the object. Partial updates go through `Patch`.
- The `Store` is mutated in place, and `run` returns it.

## Error catalogue

Every message `morphly` itself raises, with what to change.

### At import, from `@module`

```text
TypeError: compute_gross: parameter 'employees' must be annotated
```
Annotate it. Nothing is inferred.

```text
TypeError: compute_gross: unsupported annotation for 'store': <class 'morphly.store.Store'>. Expected list[Entity subclass] or a Config subclass.
```
Only two shapes are injectable. A module cannot reach for the store itself.

```text
TypeError: compute_gross: list[<class 'str'>] — the element type must be an Entity
```
`list[X]` is for entities. Scalars and parameters belong in a `Config`.

```text
TypeError: compute_gross: the return type must be annotated (use `-> None` if it writes nothing)
```
A module with no declared output has no contract.

```text
TypeError: compute_gross: annotate Patch[YourEntity], not a bare Patch
```
`list[Patch]` declares nothing. The type parameter *is* the declaration.

### At `check`

```text
LookupError: step 'report' reads Payslip, which is neither in the store nor produced by an upstream step
```
Either the step is too early, or nothing produces that type. Both are real bugs.

### At run, before applying a step

```text
TypeError: add_bonus returned Patch(Employee(name='ada'), gross) but Patch[Employee] is not in its return type
```
The module did something it never declared. Widen the return annotation, or stop doing it.

```text
ValueError: Employee has no field ['bonus']
```
A `Patch` named a field the target doesn't have — usually a typo, or a field that only exists on a
subclass.

```text
ValueError: Patch(Employee(name='ada')) has no field to write
```
An empty `Patch` is meaningless.

```text
KeyError: no Employee named 'zoe' in the store
```
The target was never stored, or an earlier step deleted it.

```text
KeyError: 'bob' is ambiguous in the lineage of Employee: Contractor, Manager
```
Two sibling types hold that name. `morphly` refuses to guess — narrow the declared type, or rename.

```text
ValueError: dp returned a Patch on Plant 'a' which the same step deletes
```
A step returned both a `Delete` and another operation on the same target. Application order is return
order, so the `Patch` would run against an object the step itself already removed. Drop one of the two.

### At run, from the store

```text
LookupError: expected exactly 1 PayrollPolicy in the store, found 0
```
Put it in the store, or bind it to the step: `Step(compute_gross, PayrollPolicy())`.

```text
LookupError: several PayrollPolicy bound to the same step
```
A step holds two configs of the same type. Keep one.

```text
TypeError: 'ada' is neither an Entity nor a Config
```
`Store` takes entities and configs, nothing else.

### On apply, from pydantic

```text
1 validation error for Employee
gross
  Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='lots', input_type=str]
```
`validate_assignment=True` means a `Patch` is validated like any other field write. Your business
invariants — validators, constrained types — apply to everything a module writes.
