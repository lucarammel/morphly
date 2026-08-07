---
title: morph
---

# morph

`morph` chains **independent modules** over a **shared set of business objects**. Each module is one
annotated function — its signature *is* the contract: what it reads, what it creates, what it changes.

```python
@module
def withhold(employees: list[Employee], policy: PayrollPolicy) -> list[Payslip]: ...
```

No base class to inherit from, no registry to keep in sync, no `get_objects_used()` to write by hand and
forget to update. One dependency: `pydantic`. Python ≥ 3.12.

## Four things worth knowing

- **The type is the key.** Reading `list[Employee]` returns every `Manager` too, subclasses included —
  nothing to register anywhere to make that work.
- **The signature is the contract.** `-> list[Payslip]` creates, `-> list[Patch[X]]` updates, `->
  list[Delete[X]]` deletes. Returning anything else is an error.
- **Nothing runs before the chain is checked.** A step reading a type nobody provides fails in a
  millisecond, not after three hours of computation.
- **Modules are isolated.** They receive copies of what they read; only the operations they return are
  applied.

See all four built into a real pipeline, one step at a time, in [Getting started](getting-started.md).

## Why not a hand-rolled orchestrator

Hand-rolled orchestrators all converge on the same flaws. `morph` refuses them by construction.

| Classic flaw | What `morph` does instead |
|---|---|
| Global `enum -> class` registry to update for every new object | The **type is the key**. Nothing to register. |
| Changes carried around as unvalidated `dict[str, Any]` | A module returns typed **pydantic objects** or `Patch` values. |
| 5–6 abstract plumbing methods per module | A module is **one annotated function**. |
| Requirements declared by hand (`get_objects_used()`) and never checked | The requirements **are** the signature, and they're checked. |
| Manual by-name reference resolution in the handler | The objects read are the objects in the `Store`. |
| Mutations that leak from one module to another | Only the **return value** is applied. |
| `deepcopy` of the whole state on every step | Copy of the **subset actually read**, and it can be turned off. |

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
