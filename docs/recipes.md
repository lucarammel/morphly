# Recipes

Task-oriented answers. All of them continue the payroll example from
[Getting started](getting-started.md).

## Run the same module twice with different parameters

Bind the config to the step rather than to the store.

```python
Pipeline(
    withhold,
    Step(report, ReportPolicy(detailed=False), name="summary"),
    Step(report, ReportPolicy(detailed=True), name="audit_log"),
)
```

Without an explicit `name`, the second occurrence is suffixed automatically (`report`, `report_2`). Names
only matter for `explain()` and `on_step`, so name them when you'll read them in logs.

## Unit-test a module without a pipeline

A module is callable on a store and returns its operations **without applying them**. No mocks, no
fixtures, no pipeline.

```python
def test_overtime_is_paid_at_1_25():
    store = Store(
        Employee(name="ada", hourly_rate=50.0),
        Timesheet(name="ada-w1", employee="ada", hours=38.0),
        PayrollPolicy(),
    )

    (patch,) = compute_gross(store)

    assert patch.fields == {"gross": 1937.50}
    assert store.find(Employee, "ada").gross == 0.0  # nothing was written
```

Pass step configs as the second argument when you don't want them in the store:

```python
ops = compute_gross(store, (PayrollPolicy(overtime_rate=1.5),))
```

## Run without touching the original store

`run` mutates in place. Copy first when you need the input state afterwards — comparing scenarios,
re-running with different parameters, keeping a before/after.

```python
after = pipeline.run(copy.deepcopy(store))
```

## Compare scenarios

No scenario machinery in the library: a loop over configs is a loop over configs.

```python
results = {
    rate: Pipeline(compute_gross, Step(withhold, PayrollPolicy(social_rate=rate))).run(copy.deepcopy(store))
    for rate in (0.20, 0.22, 0.25)
}

{rate: sum(s.net for s in st.all(Payslip)) for rate, st in results.items()}
```

## Log or trace a run

```python
pipeline.run(store, on_step=lambda step, ops, store: log.info("%s: %d ops", step.name, len(ops)))
```

```text
compute_gross: 2 ops
withhold: 2 ops
archive: 2 ops
```

`ops` is the list of `Patch`/`Delete`/entity operations the step just wrote — useful for a business log
(`f"{len(ops)} {type(ops[0]).__name__}"`) or for spotting a step that silently did nothing. The same hook
covers progress bars, metrics, and writing intermediate results:

```python
def checkpoint(step: Step, ops: list, store: Store) -> None:
    Path(f"out/{step.name}.json").write_text(json.dumps([s.model_dump() for s in store.all(Payslip)]))


pipeline.run(store, on_step=checkpoint)
```

## Load a `Config` from a file

`Config` is a plain pydantic model, so this needs nothing from `morph`:

```python
policy = PayrollPolicy.model_validate(tomllib.loads(Path("payroll.toml").read_text()))
store.put(policy)
```

Same shape for YAML, JSON, environment variables, or a settings service — all validated on the way in.

## Give a module its own working fields

When a module needs fields nobody else cares about, don't put them on the shared type. Build a local
view.

```python
class EmployeeWithHours(Employee):
    worked: float


@module
def compute_gross(employees: list[Employee], sheets: list[Timesheet]) -> list[Patch[Employee]]:
    hours = {s.employee: s.hours for s in sheets}
    rich = [view(EmployeeWithHours, e, worked=hours.get(e.name, 0.0)) for e in employees]
    return [Patch(e, gross=e.hourly_rate * e.worked) for e in rich]
```

`EmployeeWithHours` is never stored. The `Patch` still lands on the right `Employee`, because targets are
resolved against the type in the return annotation.

## Write a read-only step

Return `None`. Exports, dashboards, metrics, assertions on the state.

```python
@module
def check_payroll_balances(slips: list[Payslip], employees: list[Employee]) -> None:
    total_gross = sum(e.gross for e in employees)
    total_slips = sum(s.gross for s in slips)
    if abs(total_gross - total_slips) > 0.01:
        raise ValueError(f"payroll does not balance: {total_gross} vs {total_slips}")
```

A read-only module still declares its reads, so `check` still verifies them.

## Fail at startup, before loading any data

`check` only looks at types, so run it against a store built from your schema — no data needed.

```python
def validate_config_at_boot() -> None:
    pipeline.check(Store(PayrollPolicy(), *(cls(name="_probe") for cls in SEEDED_TYPES)))
```

Cheaper still: put it in a test. The pipeline's shape is static, so a wrong order is a unit-test failure,
not a production incident.

## Branch, loop, or run pipelines in sequence

There's no control flow in `Pipeline` because Python already has it.

```python
def run_payroll(store: Store, *, with_bonuses: bool) -> Store:
    Pipeline(compute_gross).run(store)
    if with_bonuses:
        Pipeline(add_bonus).run(store)
    return Pipeline(withhold, archive, report).run(store)
```

## Speed up a large run

The default deep-copies every injected value. If profiling says that dominates, turn it off:

```python
pipeline.run(store, copy_inputs=False)
```

Modules then receive the stored objects themselves, and mutating an input **does** change the shared
state. Measure first; the isolation guarantee is worth more than most of what it costs.

## Skip unchanged steps while iterating in a notebook

Editing step 12 and rerunning the whole pipeline recomputes steps 1–11 for nothing if their inputs haven't
moved. `reuse` skips them:

```python
store = loaded_store()
pipeline.run(store)

# ... tweak add_bonus, rerun from scratch ...
store = loaded_store()
pipeline.run(store, reuse=pipeline.last_run)  # compute_gross: skipped, add_bonus onward: runs
```

The cache lives on the `Pipeline` object, in memory, for as long as the process runs. Nothing is persisted
between processes — see [Snapshot and restore](#snapshot-and-restore) for that.

## Snapshot and restore

The store is a plain Python object.

```python
before = copy.deepcopy(store)
pipeline.run(store)
# ... something went wrong
store = before
```

For persistence between processes, `pickle` works. There is no built-in serialization format — see
[Non-goals](non-goals.md).
