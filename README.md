<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <img src="assets/logo-light.svg" alt="morph" width="200">
</picture>

**Independent modules. A shared set of business objects. A contract you can read in the signature.**

[![CI](https://github.com/lucarammel/morph/actions/workflows/ci.yml/badge.svg)](https://github.com/lucarammel/morph/actions/workflows/ci.yml)
[![coverage](./coverage.svg)](https://github.com/lucarammel/morph/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

 [Example](#example) · [Installation](#installation) · [Concepts](#concepts)

</div>

---

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

The core fits in **two files**. No enum, no name-to-class mapping, no registry to keep in sync:

- **the type is the key** — reading `list[X]` returns everything stored under `X`, subclasses included;
- **the signature is the contract** — the return type declares what's created (`Order`), updated (`Patch[X]`) or deleted (`Delete[X]`);
- **`check` before `run`** — a module reading a type nobody provides fails in a millisecond, not after three hours of computation;
- **isolation by default** — inputs are copied, only the return value is applied, a step never applies halfway.

## Why

Hand-rolled orchestrators all converge on the same flaws. `morph` refuses them by construction.

| Classic flaw | What `morph` does instead |
|---|---|
| Global `enum → class` registry to keep in sync | The type is the key. Nothing to register. |
| Changes carried around as unvalidated `dict[str, Any]` | Typed pydantic objects or `Patch` values. |
| 5–6 abstract plumbing methods per module | One annotated function. |
| Requirements declared by hand and never checked | The requirements **are** the signature, and they're checked. |
| Mutations that leak from one module to another | Only the return value is applied. |
| `deepcopy` of the whole state on every step | Copy of the subset actually read, and it can be turned off. |

## Installation

```bash
uv add git+https://github.com/lucarammel/morph
```

One dependency: `pydantic>=2.9`. Python ≥ 3.12.

## Concepts

| | |
|---|---|
| **`Entity`** | A shared business object, identified by `name` within its type lineage. |
| **`Config`** | A singleton input: module parameters, global settings. |
| **`Store`** | The shared state. Buckets by type, read by type (subclasses included). |
| **`Patch[E]` / `Delete[E]`** | Partial update / deletion, returned by a module. |
| **`@module`** | An annotated function becomes a module: its annotations are its contract. |
| **`Pipeline`** | An ordered list of steps, validated before it runs. |


## Development

```bash
uv sync
uv run pytest --cov=morph     # tests + coverage
uv run ruff check morph tests # lint
uv run ruff format morph tests
uv run ty check                # type checking
uv run --group docs zensical serve  # docs locally on localhost:8000
```

## License

[MIT](LICENSE)
