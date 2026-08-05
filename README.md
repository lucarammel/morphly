<div align="center">

# morph

**Des modules indépendants. Un jeu d'objets métier partagé. Un contrat lisible dans la signature.**

[![CI](https://github.com/lucarammel/morph/actions/workflows/ci.yml/badge.svg)](https://github.com/lucarammel/morph/actions/workflows/ci.yml)
[![coverage](./coverage.svg)](https://github.com/lucarammel/morph/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Spécification complète](SPEC.md) · [Exemple](#exemple) · [Installation](#installation) · [Concepts](#concepts)

</div>

---

## Exemple

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

Le noyau tient en **deux fichiers**. Pas d'enum, pas de mapping nom→classe, pas de registre à tenir à jour :

- **le type est la clé** — lire `list[X]` renvoie tout ce qui est stocké sous `X`, sous-classes incluses ;
- **la signature est le contrat** — le retour déclare ce qui est créé (`Order`), mis à jour (`Patch[X]`) ou supprimé (`Delete[X]`) ;
- **`check` avant `run`** — un module qui lit un type que personne ne fournit échoue en une milliseconde, pas après trois heures de calcul ;
- **isolation par défaut** — les entrées sont copiées, seul le retour est appliqué, une étape ne s'applique pas à moitié.

## Pourquoi

Les orchestrateurs maison convergent tous vers les mêmes défauts. `morph` les refuse par construction.

| Défaut classique | Ce que fait `morph` |
|---|---|
| Registre global `enum → classe` à tenir à jour | Le type est la clé. Rien à enregistrer. |
| Modifications transportées en `dict[str, Any]` non validé | Des objets pydantic ou des `Patch` typés. |
| 5–6 méthodes abstraites de plomberie par module | Une fonction annotée. |
| Besoins déclarés à la main et jamais vérifiés | Les besoins **sont** la signature, et sont vérifiés. |
| Mutations qui fuient d'un module à l'autre | Seul le retour est appliqué. |
| `deepcopy` de tout l'état à chaque étape | Copie du seul sous-ensemble lu, désactivable. |

## Installation

```bash
uv add git+https://github.com/lucarammel/morph
```

Une seule dépendance : `pydantic>=2.9`. Python ≥ 3.13.

## Concepts

| | |
|---|---|
| **`Entity`** | Objet métier partagé, identifié par `name` au sein de sa lignée de types. |
| **`Config`** | Entrée singleton : paramètres d'un module, réglages globaux. |
| **`Store`** | L'état partagé. Buckets par type, lecture par type (sous-classes incluses). |
| **`Patch[E]` / `Delete[E]`** | Mise à jour partielle / suppression, retournées par un module. |
| **`@module`** | Une fonction annotée devient un module : ses annotations sont son contrat. |
| **`Pipeline`** | Une liste ordonnée d'étapes, validée avant d'être exécutée. |

Détails, règles de validation, non-objectifs et plan d'adoption : **[SPEC.md](SPEC.md)**.

## Développement

```bash
uv sync
uv run pytest --cov=morph     # tests + couverture
uv run ruff check morph tests # lint
uv run ruff format morph tests
uv run ty check                # typage
```

## Licence

[MIT](LICENSE)
