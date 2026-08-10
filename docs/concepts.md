# Concepts

Six of them, and two are a matched pair. Examples continue the payroll run from
[Getting started](getting-started.md).

## `Entity`

A shared business object, identified by `name` **within its type lineage**.

```python
class Employee(Entity):
    hourly_rate: float
    contract_hours: float = 35.0
    gross: float = 0.0
```

- `Entity` inherits from `pydantic.BaseModel` and enforces `name: str` (frozen).
- It enables `validate_assignment=True`, so every field write is validated — including the ones a `Patch`
  applies — and `arbitrary_types_allowed=True`, so a field can carry a non-pydantic object: a dataframe, a
  matrix, a solver handle.
- Identity is the `(type, name)` pair.

### Lineage

Subclasses are a first-class case, not an edge case.

```python
class Manager(Employee):
    bonus_target: float
```

| Read | Returns |
|---|---|
| `list[Employee]` | every `Employee` **and** every `Manager` |
| `list[Manager]` | only the managers |

That's what lets a payroll module written before `Manager` existed keep paying managers correctly. It also
means a `Patch[Employee]` can legitimately target a `Manager`: the target is resolved against the declared
type and found anywhere in its lineage.

The one rule this creates: two objects with the same `name` in two **sibling** types are ambiguous, and
`morphly` says so instead of picking one.

```python
store.find(Employee, "bob")
# KeyError: 'bob' is ambiguous in the lineage of Employee: Contractor, Manager
```

## `Config`

A **singleton** input: module parameters, rates, thresholds, global context.

```python
class PayrollPolicy(Config):
    overtime_after: float = 35.0
    overtime_rate: float = 1.25
    social_rate: float = 0.22
```

No `name`, because there is only ever one of each type in play. It is resolved by type, first from the
step it is bound to, then from the `Store` — see
[Step](modules-and-workflows.md#step-per-step-configuration).

A `Config` is an ordinary pydantic model, so loading one from a file is a one-liner and needs nothing from
`morphly`:

```python
PayrollPolicy.model_validate(tomllib.loads(Path("payroll.toml").read_text()))
```

## `Store`

The shared state. Buckets by concrete type, read by type.

| Method | Effect |
|---|---|
| `Store(*items)` | Builds and fills. |
| `put(*items)` | Upsert. `Entity` → key `(type, name)`. `Config` → key `type`. |
| `all(cls)` | Every instance of `cls` and its subclasses. |
| `one(cls)` | The single instance of `Config` `cls`. `LookupError` if 0 or > 1. |
| `find(cls, name)` | The object named `name`: exact type first, then the lineage of `cls`. |
| `drop(target)` | Removes the targeted object. |
| `patch(target, fields)` | Writes the targeted fields onto the object in the store. |
| `types()` | Types currently present — the starting point of `check`. |

```python
store = Store(
    Employee(name="ada", hourly_rate=50.0),
    Manager(name="bob", hourly_rate=60.0, bonus_target=0.10),
    PayrollPolicy(),
)

store  # Store(Employee=1, Manager=1; PayrollPolicy)
store.all(Employee)  # [Employee(name='ada'), Manager(name='bob')]
store.one(PayrollPolicy).social_rate  # 0.22
```

`put` **replaces** the object stored under the same `(type, name)`. Partial updates go through `Patch`.

The store is a plain Python object: `copy.deepcopy(store)` is a snapshot, `pickle` persists it.

### Target resolution

This is the part worth understanding, because everything else leans on it.

A module never holds the stored object — it holds a deep copy, and sometimes an enriched subclass of it.
So a returned `Patch` is not resolved by Python identity. It is resolved by
**(type declared in the return annotation, `name`)**:

```python
declared = next(t for t in touches if isinstance(op.target, t))  # from `-> list[Patch[Employee]]`
obj = store.find(declared, op.target.name)  # the real stored object
```

Two consequences:

- deep-copy isolation costs nothing in expressiveness — patching a copy works;
- a module can hand back a **view**, an object whose own class isn't even in the store, as long as the
  declared type is.

## `Put[E]`, `Patch[E]` and `Delete[E]`

Not business objects — **intents**. Returning one changes nothing by itself; the workflow applies it once
the whole step has been validated.

```python
Put(payslip)  # creation / full replacement
Patch(employee, gross=1937.50)  # partial update
Delete(timesheet)  # deletion
```

- `Patch` writes only the fields it's given. It's the normal output of a module that computes a few
  attributes on shared objects without touching the rest.
- Returning a full `Entity` means creation or **full replacement**. `Put` is optional sugar for exactly
  that: `Put(payslip)` and a bare `payslip` do the same thing, so use it when a return annotation is a
  union and you'd rather read the three verbs than spot a bare type among them.
- The type parameter is **required in the return annotation**: `list[Patch[Employee]]`. That's how the
  module declares it touches `Employee`. A bare `list[Patch]` is a declaration error.

```python
-> list[Payslip]                        # creates / replaces
-> list[Put[Payslip]]                   # the same, said out loud
-> list[Patch[Employee]]                # updates a few fields
-> list[Delete[Timesheet]]              # deletes
-> list[Payslip | Delete[Timesheet]]    # several operations at once
-> None                                 # touches nothing
```

## `view` (sugar)

Modules often need working fields that don't belong on the shared type — nobody else cares that the
payroll module tracked `worked` hours per employee. `view` builds a module-local enriched copy:

```python
class EmployeeWithHours(Employee):
    worked: float


@module
def compute_gross(employees: list[Employee], sheets: list[Timesheet]) -> list[Patch[Employee]]:
    hours = {s.employee: s.hours for s in sheets}
    rich = [view(EmployeeWithHours, e, worked=hours.get(e.name, 0.0)) for e in employees]
    return [Patch(e, gross=e.hourly_rate * e.worked) for e in rich]
```

It shallow-copies the source's fields, adds the extras, then validates against the target class —
replacing a hand-written `model_validate({**dump(obj), ...})` in every module. `EmployeeWithHours` is
never stored; the `Patch` still lands on the right `Employee` because the return annotation says
`Patch[Employee]`.

## `@module` and `Workflow`

The last two, covered in full on their own page:
[Modules and workflows](modules-and-workflows.md).
