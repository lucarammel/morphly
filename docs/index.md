---
title: morph
---

# morph

`morph` chains **independent modules** over a **shared set of business objects**. A module is one
annotated function: its signature declares what it reads, what it creates, and what it changes.

```python
@module
def withhold(employees: list[Employee], policy: PayrollPolicy) -> list[Payslip]: ...
```

That signature is the whole contract. There is no base class to inherit from, no registry to keep in sync,
and no `get_objects_used()` to write by hand and forget to update.

One dependency: `pydantic`. Python ≥ 3.12.

## In one example

Running payroll: hours become gross pay, managers get a bonus, gross becomes a payslip, timesheets are
archived. Four teams could own those four steps and never talk to each other.

```python
from morph import Config, Delete, Entity, Patch, Pipeline, Store, module


class Employee(Entity):
    hourly_rate: float
    contract_hours: float = 35.0
    gross: float = 0.0


class Manager(Employee):
    bonus_target: float


class Timesheet(Entity):
    employee: str
    hours: float


class Payslip(Entity):
    employee: str
    gross: float
    withheld: float
    net: float


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


@module
def add_bonus(managers: list[Manager]) -> list[Patch[Manager]]:
    return [Patch(m, gross=m.gross * (1 + m.bonus_target)) for m in managers]


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


store = Store(
    Employee(name="ada", hourly_rate=50.0),
    Manager(name="bob", hourly_rate=60.0, bonus_target=0.10),
    Timesheet(name="ada-w1", employee="ada", hours=38.0),
    Timesheet(name="bob-w1", employee="bob", hours=35.0),
    PayrollPolicy(),
)

Pipeline(compute_gross, add_bonus, withhold, archive).run(store)

store.find(Employee, "ada").gross  # 1937.50 — 35h + 3h of overtime at 1.25
store.find(Manager, "bob").gross  # 2310.00 — 35h, then +10% bonus
store.all(Payslip)  # [Payslip(name='slip-ada'), Payslip(name='slip-bob')]
store.all(Timesheet)  # []
```

Four things are worth noticing in that snippet, and they are the whole design:

- **The type is the key.** `compute_gross` asks for `list[Employee]` and gets `bob` too, because `Manager`
  is an `Employee`. Nothing was registered anywhere to make that work.
- **The signature is the contract.** `-> list[Payslip]` says *creates*, `-> list[Patch[Employee]]` says
  *updates*, `-> list[Delete[Timesheet]]` says *deletes*. Returning anything else is an error.
- **Nothing runs before the chain is checked.** Put `archive` before `compute_gross` and it still works;
  put a step reading `Payslip` before `withhold` and the pipeline refuses to start, in a millisecond.
- **Modules are isolated.** They receive copies. `compute_gross` could scribble all over its `employees`
  list and the store would not notice — only the returned `Patch` values are applied.

New to the library? Start with [Getting started](getting-started.md), which builds this pipeline one step
at a time.

## The problem it solves

Chaining N computation modules over shared business state, with:

- common business objects, typed and validated;
- modules that know neither the orchestrator nor each other;
- an explicit contract: what a module reads, what it creates, what it touches;
- a failure **before** the run when the chaining is inconsistent.

Hand-rolled orchestrators all converge on the same flaws, which `morph` refuses by construction.

| Classic flaw | What `morph` does instead |
|---|---|
| Global `enum -> class` registry to update for every new object | The **type is the key**. Nothing to register. |
| Changes carried around as unvalidated `dict[str, Any]` | A module returns typed **pydantic objects** or `Patch` values. |
| 5–6 abstract plumbing methods per module | A module is **one annotated function**. |
| Requirements declared by hand (`get_objects_used()`) and never checked | The requirements **are** the signature, and they're checked. |
| Manual by-name reference resolution in the handler | The objects read are the objects in the `Store`. |
| Mutations that leak from one module to another | Only the **return value** is applied. |
| `deepcopy` of the whole state on every step | Copy of the **subset actually read**, and it can be turned off. |

## Principles

1. **The type is the key.** No enum, no name-to-class mapping, no registry.
2. **The signature is the contract.** Annotations describe inputs and outputs; the core reads them.
3. **No implicit side effects.** Mutating an input has no effect; only the return value is applied.
4. **Fail before computing.** An inconsistent chain is a startup error.
5. **Zero ceremony.** No base class to inherit from to write a module.

## Where to go next

Read in this order the first time; jump straight to any card once you know what you're after.

<div class="grid cards" markdown>

-   :lucide-rocket:{ .lg .middle } **[Getting started](getting-started.md)**

    ---

    Build the payroll pipeline from scratch, one step at a time.

-   :lucide-layers:{ .lg .middle } **[Concepts](concepts.md)**

    ---

    `Entity`, `Config`, `Store`, `Patch`, `Delete`, `view` — the six building blocks.

-   :lucide-workflow:{ .lg .middle } **[Modules and pipelines](modules-and-pipelines.md)**

    ---

    The injection and output rules, in full.

-   :lucide-shield-check:{ .lg .middle } **[Validation](validation.md)**

    ---

    What is checked, when, and which exception you get.

-   :lucide-flask-conical:{ .lg .middle } **[Recipes](recipes.md)**

    ---

    Same module twice, unit-testing a module, snapshots, observability.

-   :lucide-code:{ .lg .middle } **[API reference](reference.md)**

    ---

    Every public symbol, generated from the source.

-   :lucide-ban:{ .lg .middle } **[Non-goals](non-goals.md)**

    ---

    What is deliberately absent, and what would justify adding it.

</div>
