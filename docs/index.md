---
title: morph
---

# morph

Independent modules over a shared set of business objects. The function signature is the contract.

```python
@module
def withhold(employees: list[Employee], policy: PayrollPolicy) -> list[Payslip]: ...
```

- **The type is the key** — no enum, no registry, no name-to-class mapping.
- **The signature is the contract** — what a module reads, creates, and touches is checked, not just documented.
- **Fails before it runs** — an inconsistent chain never reaches your data.
- **Modules are isolated** — only the return value is applied.

One dependency: `pydantic`. Python ≥ 3.12.

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
