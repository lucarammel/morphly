---
title: morph
---

# morph

`morph` orchestrates **independent modules** that share a **common set of business objects**. Each module
reads the subset of objects it needs, and declares what it changes.

One dependency: `pydantic`. Python ≥ 3.13.

## Example

```python
from morph import Config, Delete, Entity, Patch, Pipeline, Step, Store, module

class Plant(Entity):
    pmax: float
    cost: float
    cleared: float = 0.0

class Order(Entity):
    volume: float
    price: float

class BidParams(Config):
    margin: float = 1.0

@module
def bidding(plants: list[Plant], params: BidParams) -> list[Order]:
    return [Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost * params.margin) for p in plants]

@module
def clearing(orders: list[Order], plants: list[Plant]) -> list[Patch[Plant] | Delete[Order]]:
    by_order = {f"o_{p.name}": p for p in plants}
    return [
        Patch(by_order[o.name], cleared=o.volume) if o.price < 30 else Delete(o)
        for o in orders
    ]

store = Store(Plant(name="a", pmax=100, cost=10), Plant(name="b", pmax=50, cost=40))
Pipeline(Step(bidding, BidParams(margin=1.2)), clearing).run(store)
```

## Problem

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

For the full concepts and validation rules, see [Concepts](concepts.md),
[Modules and pipelines](modules-and-pipelines.md) and [Validation](validation.md).
