---
title: morphly
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

# morphly<span class="hero-accent">()</span>

Independent modules chained into a typed workflow over a shared set of business objects.
**Each step's signature is its contract.**

</div>

<div class="hero-points" markdown>

- **Checked before it runs** — an inconsistent workflow never reaches your data.
- **The signature is the contract** — what each step reads, creates, and touches.
- **The type is the key** — no enum, no registry.
- **Steps are isolated** — only the return value is applied.

</div>

## Where to go next

Read in this order the first time; jump straight to any card once you know what you're after.

<div class="grid cards" markdown>

-   :lucide-rocket:{ .lg .middle } **[Getting started](getting-started.md)**

    ---

    Build the payroll workflow from scratch, one step at a time.

-   :lucide-layers:{ .lg .middle } **[Concepts](concepts.md)**

    ---

    `Entity`, `Config`, `Store`, `Patch`, `Delete`, `view` — the six building blocks.

-   :lucide-workflow:{ .lg .middle } **[Modules and workflows](modules-and-workflows.md)**

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
