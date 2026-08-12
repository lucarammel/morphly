<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <img src="assets/logo-light.svg" alt="morphly" width="200">
</picture>

**Independent modules, chained into a typed workflow, over a shared set of business objects.**

[![testing](https://github.com/lucarammel/morphly/actions/workflows/test.yml/badge.svg)](https://github.com/lucarammel/morphly/actions/workflows/test.yml)
[![coverage](https://codecov.io/gh/lucarammel/morphly/graph/badge.svg)](https://codecov.io/gh/lucarammel/morphly)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![docs](https://img.shields.io/badge/docs-lucarammel.github.io-6c63ff)](https://lucarammel.github.io/morphly/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Why](#why-morphly) · [Example](#example) · [Installation](#installation) · [Documentation](https://lucarammel.github.io/morphly/)

</div>

---

## Why morphly

Every team ends up writing the same thing: a handful of steps that read and update a shared set of
business objects — a payroll run, an order pipeline, a simulation with several stages. The orchestration
code always rots the same way too: a registry mapping names to classes, `dict[str, Any]` ferried between
steps, and a `KeyError` three hours into a batch job because step 12 needed something step 4 forgot to
produce.

`morphly` turns each step into **one annotated Python function**. The signature — what it reads, creates,
and touches — is the entire contract, and it's checked before any of your code runs, not discovered when it
crashes.

- **Typed by construction** — pydantic objects in, pydantic objects out. No untyped payloads passed between steps.
- **The signature is the contract** — reads, creates, and touches are declared in the annotations, and enforced.
- **Fails in milliseconds, not hours** — an inconsistent workflow is rejected before it touches your data.
- **Zero registries** — the type is the key. Nothing to register when you add a business object.
- **Isolated by default** — a module receives copies; only what it returns is applied. No mutation leaking between steps.

## Example

```python
from morphly import Config, Entity, Patch, Store, Workflow, module


class Employee(Entity):
    hourly_rate: float


class Timesheet(Entity):
    employee: str
    hours: float


class Payslip(Entity):
    gross: float
    net: float = 0.0


class PayrollPolicy(Config):
    tax_rate: float = 0.22


@module
def issue_payslip(employees: list[Employee], sheets: list[Timesheet]) -> list[Payslip]:
    hours = {s.employee: s.hours for s in sheets}
    return [Payslip(name=f"slip-{e.name}", gross=e.hourly_rate * hours.get(e.name, 0.0)) for e in employees]


@module
def withhold_tax(slips: list[Payslip], policy: PayrollPolicy) -> list[Patch[Payslip]]:
    return [Patch(s, net=s.gross * (1 - policy.tax_rate)) for s in slips]


store = Store(
    Employee(name="ada", hourly_rate=50.0),
    Timesheet(name="ada-w1", employee="ada", hours=40.0),
    PayrollPolicy(),
)

Workflow(issue_payslip, withhold_tax).run(store)

store.find(Payslip, "slip-ada").net  # 1560.0 — 2000 gross, 22% withheld
```

## Installation

```bash
uv add morphly  # with uv

pip install morphly  # with pip
```

## How it stacks up

Hand-rolled orchestrators all converge on the same flaws. `morphly` refuses them by construction.

| Classic flaw | What `morphly` does instead |
|---|---|
| Global `enum → class` registry to keep in sync | The type is the key. Nothing to register. |
| Changes carried around as unvalidated `dict[str, Any]` | Typed pydantic objects or `Patch` values. |
| 5–6 abstract plumbing methods per module | One annotated function. |
| Requirements declared by hand and never checked | The requirements **are** the signature, and they're checked. |
| Mutations that leak from one module to another | Only the return value is applied. |
| `deepcopy` of the whole state on every step | Copy of the subset actually read, and it can be turned off. |

## Concepts

| | |
|---|---|
| **`Entity`** | A shared business object, identified by `name` within its type lineage. |
| **`Config`** | A singleton input: module parameters, global settings. |
| **`Store`** | The shared state. Buckets by type, read by type (subclasses included). |
| **`Put[E]` / `Patch[E]` / `Delete[E]`** | Creation / partial update / deletion, returned by a module. |
| **`@module`** | An annotated function becomes a module: its annotations are its contract. |
| **`Workflow`** | An ordered list of steps, validated before it runs. |

Full walkthrough, the injection/output rules, validation, and recipes: **[lucarammel.github.io/morphly](https://lucarammel.github.io/morphly/)**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## License

[MIT](LICENSE)
