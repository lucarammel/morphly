# Concepts

## `Entity`

Objet métier partagé, identifié par `name` **au sein de sa lignée de types**.

```python
class Plant(Entity):
    pmax: float
    cost: float
```

- `Entity` hérite de `pydantic.BaseModel`, impose `name: str` (frozen), et active
  `validate_assignment=True` (toute écriture de champ est validée) et `arbitrary_types_allowed=True`
  (champs porteurs d'objets non-pydantic : timeseries, matrices, handles de solveur).
- L'identité est le couple `(type, name)`.
- Les sous-classes sont un cas de première classe : lire `list[Plant]` renvoie aussi les `ThermalPlant`.

## `Config`

Entrée **singleton** : paramètres d'un module, réglages globaux, contexte.

```python
class BidParams(Config):
    margin: float = 1.0
```

Pas de `name`. Résolu par type, soit sur l'étape, soit dans le `Store` — voir
[Step](modules-and-pipelines.md#step-configuration-par-etape).

## `Store`

L'état partagé. Buckets par type concret, lecture par type (sous-classes incluses).

| Méthode | Effet |
|---|---|
| `Store(*items)` | Construit et remplit. |
| `put(*items)` | Upsert. `Entity` → clé `(type, name)`. `Config` → clé `type`. |
| `all(cls)` | Toutes les instances de `cls` et de ses sous-classes. |
| `one(cls)` | L'unique instance de `Config` `cls`. `LookupError` si 0 ou > 1. |
| `find(cls, name)` | L'objet nommé `name` : type exact d'abord, puis lignée de `cls`. `KeyError` si absent ou ambigu. |
| `drop(target)` | Supprime l'objet visé. |
| `patch(target, fields)` | Écrit les champs visés sur l'objet du `Store`. |
| `types()` | Types présents. |

**Résolution des cibles.** Un module travaille souvent sur une *vue* enrichie (`MarketAreaMC(MarketArea)`),
et renvoie `Patch(mc_area, price=...)`. La cible est résolue sur le type **déclaré dans l'annotation de
retour** (`Patch[MarketArea]`), pas sur la classe de la vue : la vue peut donc être une sœur du type stocké.
`Store.find` cherche d'abord le bucket du type exact, puis la lignée ; l'ambiguïté (deux objets de même
`name` dans deux types frères) est une erreur explicite, pas un choix arbitraire.

Le `Store` est un objet Python ordinaire : `copy.deepcopy(store)` est un snapshot, `pickle` le persiste.

## `Patch[E]` et `Delete[E]`

```python
Patch(order, accepted_power=ts, spread=0.3)   # mise à jour partielle
Delete(order)                                 # suppression
```

- `Patch` n'écrit que les champs fournis — c'est la sortie normale d'un module qui calcule quelques
  attributs sur des objets existants sans toucher au reste (ni aux références vers lui).
- Renvoyer une `Entity` complète = création ou **remplacement intégral**.
- Le paramètre de type est **obligatoire dans l'annotation de retour** : `list[Patch[Order]]`. C'est ainsi
  que le module déclare qu'il touche `Order`. `list[Patch]` nu est une erreur de déclaration.

## `view` (sucre)

```python
mc_order = view(OrderMC, order, times=times, timestep=timestep)
```

Construit une vue enrichie à partir d'une entité partagée : copie superficielle des champs de la source,
plus les extras, puis validation pydantic de la classe cible. Remplace le
`model_validate({**shallow_dump(obj), ...})` écrit à la main dans chaque module.
