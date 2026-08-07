# Getting started

We'll build a payroll run: timesheets in, payslips out. By the end you'll have used every concept in the
library, and there are only six.

## Install

```bash
uv add git+https://github.com/lucarammel/morphly
```

One dependency, `pydantic>=2.9`. Python ≥ 3.12.

## 1. Describe the business objects

An [`Entity`][morphly.Entity] is a shared business object. It's a pydantic model with one thing enforced: a
frozen `name` that identifies it.

```python
from morphly import Entity


class Employee(Entity):
    hourly_rate: float
    contract_hours: float = 35.0
    gross: float = 0.0


class Timesheet(Entity):
    employee: str
    hours: float
```

`name` is the identity — `"ada"`, `"ada-w1"`. Everything else is yours, validated by pydantic like any
model.

## 2. Fill a store

The [`Store`][morphly.Store] holds the shared state. You build it from your own loading code — a database, a
CSV, an API — `morphly` does not care where the objects come from.

```python
from morphly import Store

store = Store(
    Employee(name="ada", hourly_rate=50.0),
    Timesheet(name="ada-w1", employee="ada", hours=38.0),
)

store.all(Employee)  # [Employee(name='ada')]
store  # Store(Employee=1, Timesheet=1)
```

Objects are filed by type. There is no name to declare, no enum to extend, no registry: `Employee` *is*
the key.

## 3. Write the first module

A module is a function with `@module` on it. Annotate the parameters with what you want to read, and the
return type with what you intend to change.

```python
from morphly import Patch, module


@module
def compute_gross(employees: list[Employee], sheets: list[Timesheet]) -> list[Patch[Employee]]:
    worked = {s.employee: s.hours for s in sheets}
    return [Patch(e, gross=e.hourly_rate * worked.get(e.name, 0.0)) for e in employees]
```

Read that signature as a sentence: *reads every `Employee` and every `Timesheet`, updates some fields on
`Employee` objects*. That sentence is machine-readable, and it's the only declaration you will write.

A [`Patch`][morphly.Patch] writes the fields you name and nothing else. It doesn't modify anything by
itself — it's an intent handed back to the workflow.

!!! note "Why not just mutate the employee?"
    You can — the object is right there. It just won't do anything. Modules receive **copies**, and only
    the returned operations are applied. That's what makes a module safe to write without knowing what
    the other modules do.

## 4. Run it

```python
from morphly import Workflow

Workflow(compute_gross).run(store)

store.find(Employee, "ada").gross  # 1900.0
```

[`Workflow.run`][morphly.Workflow.run] mutates the store and returns it. Steps run in the order you gave.

## 5. Move the parameters into a `Config`

Overtime rules don't belong hard-coded in a module. A [`Config`][morphly.Config] is a singleton input,
resolved by type — no `name`, because there's only ever one.

```python
from morphly import Config


class PayrollPolicy(Config):
    overtime_after: float = 35.0
    overtime_rate: float = 1.25
    social_rate: float = 0.22


@module
def compute_gross(
    employees: list[Employee],
    sheets: list[Timesheet],
    policy: PayrollPolicy,
) -> list[Patch[Employee]]:
    worked: dict[str, float] = {}
    for s in sheets:
        worked[s.employee] = worked.get(s.employee, 0.0) + s.hours
    patches = []
    for e in employees:
        hours = worked.get(e.name, 0.0)
        overtime = max(0.0, hours - policy.overtime_after)
        paid = (hours - overtime) + overtime * policy.overtime_rate
        patches.append(Patch(e, gross=e.hourly_rate * paid))
    return patches
```

Put the policy in the store and it's injected:

```python
store.put(PayrollPolicy())
Workflow(compute_gross).run(store)

store.find(Employee, "ada").gross  # 1937.50 — 35h + 3h at 1.25
```

A config can also be bound to one specific step, which is how the same module runs twice with different
parameters — see [Step](modules-and-workflows.md#step-per-step-configuration).

## 6. Subclasses come for free

Managers are employees with a bonus. Subclass, and every module reading `list[Employee]` picks them up
without changing a line.

```python
class Manager(Employee):
    bonus_target: float


@module
def add_bonus(managers: list[Manager]) -> list[Patch[Manager]]:
    return [Patch(m, gross=m.gross * (1 + m.bonus_target)) for m in managers]
```

```python
store.put(Manager(name="bob", hourly_rate=60.0, bonus_target=0.10))
store.put(Timesheet(name="bob-w1", employee="bob", hours=35.0))

Workflow(compute_gross, add_bonus).run(store)

store.find(Manager, "bob").gross  # 2310.00 — 2100 of gross, then +10%
```

`compute_gross` never mentions `Manager` and still paid `bob`: reading a type reads its whole lineage.
`add_bonus` narrows to `list[Manager]` and sees only the managers.

## 7. Create and delete

Returning a full entity **creates or replaces** it. Returning a [`Delete`][morphly.Delete] removes it.

```python
from morphly import Delete


class Payslip(Entity):
    employee: str
    gross: float
    withheld: float
    net: float


@module
def withhold(employees: list[Employee], policy: PayrollPolicy) -> list[Payslip]:
    return [
        Payslip(
            name=f"slip-{e.name}",
            employee=e.name,
            gross=e.gross,
            withheld=e.gross * policy.social_rate,
            net=e.gross * (1 - policy.social_rate),
        )
        for e in employees
    ]


@module
def archive(sheets: list[Timesheet]) -> list[Delete[Timesheet]]:
    return [Delete(s) for s in sheets]
```

Note the difference the contract draws: `Payslip` is **produced** — it needn't exist yet — while
`Delete[Timesheet]` **touches** a type that must already be there.

## 8. A read-only step, and the check that earns its keep

A module returning `None` writes nothing. Exports, metrics, monitoring.

```python
@module
def report(slips: list[Payslip]) -> None:
    print(f"{len(slips)} payslips, net total {sum(s.net for s in slips):.2f}")
```

Rebuild the store from scratch before the full run — `add_bonus` multiplies `gross`, so replaying it over
a store that already went through the workflow would pay `bob` his bonus twice. A run starts from loaded
data, not from its own output:

```python
def loaded_store() -> Store:
    return Store(
        Employee(name="ada", hourly_rate=50.0),
        Manager(name="bob", hourly_rate=60.0, bonus_target=0.10),
        Timesheet(name="ada-w1", employee="ada", hours=38.0),
        Timesheet(name="bob-w1", employee="bob", hours=35.0),
        PayrollPolicy(),
    )


store = loaded_store()
workflow = Workflow(compute_gross, add_bonus, withhold, archive, report)
workflow.run(store)
# 2 payslips, net total 3313.05
```

Get the order wrong and nothing runs at all:

```python
Workflow(report, withhold).check(loaded_store())
# LookupError: step 'report' reads Payslip, which is neither in the store
#              nor produced by an upstream step
```

Note the freshly loaded store in that last call: `check` only asks *which types are present*, and by now
`store` holds the payslips the run just created — the mistake would slip through. That's the honest limit
of the check, and it's spelled out in [Validation](validation.md#what-check-does-not-catch).

[`check`][morphly.Workflow.check] replays the workflow on **types only**, no computation. `run` calls it
first, so a workflow that would fail three hours in fails before it starts. You can also call it yourself
at startup, before loading any data.

## 9. See what you built

```python
print(workflow.explain())
```

```text
1. compute_gross: compute_gross(Employee[], Timesheet[], PayrollPolicy) -> ~Employee
2. add_bonus: add_bonus(Manager[]) -> ~Manager
3. withhold: withhold(Employee[], PayrollPolicy) -> Payslip
4. archive: archive(Timesheet[]) -> ~Timesheet
5. report: report(Payslip[]) -> -
```

`[]` marks a collection read, `~` a touched type, and a bare name a produced one. This is read straight
from the signatures, so it can never be out of date.

## That's the whole library

Six concepts: `Entity`, `Config`, `Store`, `Patch`/`Delete`, `@module`, `Workflow`.

- The full injection and output rules: [Modules and workflows](modules-and-workflows.md).
- Everything that gets checked, and when: [Validation](validation.md).
- Running a module twice, unit tests, snapshots, logging: [Recipes](recipes.md).
