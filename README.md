# morph

![CI](https://github.com/lucarammel/morph/actions/workflows/ci.yml/badge.svg)
![coverage](./coverage.svg)
![python](https://img.shields.io/badge/python-3.13%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Des modules indépendants, un jeu d'objets métier partagé, un contrat lisible dans la signature.

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

Le noyau tient en deux fichiers. Ce qu'il fait :

- **le type est la clé** — pas d'enum, pas de mapping nom→classe, pas de registre à tenir à jour ;
- **la signature est le contrat** — `list[X]` lit, le retour déclare ce qui est créé (`Order`), mis à jour (`Patch[X]`) ou supprimé (`Delete[X]`) ;
- **`check` avant `run`** — un module qui lit un type que personne ne fournit échoue en une milliseconde, pas après trois heures de calcul ;
- **isolation** — les entrées sont copiées, seul le retour est appliqué, une étape ne s'applique pas à moitié.

Spécification complète, règles de validation, non-objectifs et plan d'adoption : [SPEC.md](SPEC.md).

```bash
uv sync
uv run pytest
```
