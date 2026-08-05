---
title: morph
---

# morph

`morph` orchestre des **modules indépendants** qui partagent un **jeu d'objets métier communs**. Chaque
module lit le sous-ensemble d'objets dont il a besoin, et déclare ce qu'il modifie.

Une seule dépendance : `pydantic`. Python ≥ 3.13.

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

## Problème

Chaîner N modules de calcul sur un état métier partagé, avec :

- des objets métier communs, typés et validés ;
- des modules qui ne connaissent ni l'orchestrateur ni les autres modules ;
- un contrat explicite : ce qu'un module lit, ce qu'il crée, ce qu'il touche ;
- un échec **avant** le calcul quand le chaînage est incohérent.

Les orchestrateurs maison convergent tous vers les mêmes défauts, que `morph` refuse par construction.

| Défaut classique | Ce que fait `morph` |
|---|---|
| Registre global `enum -> classe` à modifier pour chaque nouvel objet | Le **type est la clé**. Rien à enregistrer. |
| Modifications transportées en `dict[str, Any]` non validés | Un module renvoie des **objets pydantic** ou des `Patch` typés. |
| 5–6 méthodes abstraites de plomberie par module | Un module est **une fonction annotée**. |
| Besoins déclarés à la main (`get_objects_used()`) et jamais vérifiés | Les besoins **sont** la signature, et ils sont vérifiés. |
| Résolution de références par nom, à la main, dans le handler | Les objets lus sont les objets du `Store`. |
| Mutations qui fuient d'un module à l'autre | Seul le **retour** est appliqué. |
| `deepcopy` de tout l'état à chaque étape | Copie du **seul sous-ensemble lu**, désactivable. |

## Principes

1. **Le type est la clé.** Pas d'enum, pas de mapping nom→classe, pas de registre.
2. **La signature est le contrat.** Les annotations décrivent entrées et sorties ; le noyau les lit.
3. **Pas d'effet de bord implicite.** Muter une entrée n'a aucun effet ; seul le retour est appliqué.
4. **Échouer avant de calculer.** Une incohérence de chaînage est une erreur au démarrage.
5. **Zéro cérémonie.** Aucune classe à hériter pour écrire un module.

Pour le détail des concepts et des règles de validation, voir [Concepts](concepts.md),
[Modules et pipelines](modules-and-pipelines.md) et [Validation](validation.md).
