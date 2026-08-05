# Modules et pipelines

Un module est une fonction décorée par `@module`.

```python
@module
def bidding(plants: list[Plant], params: BidParams) -> list[Order]:
    return [Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost * params.margin) for p in plants]
```

## Règles d'injection (paramètres)

| Annotation | Reçoit | Erreur |
|---|---|---|
| `list[X]`, `X: Entity` | `store.all(X)` — liste, éventuellement vide | `TypeError` si `X` n'est pas une `Entity` |
| `X`, `X: Config` | la config de l'étape, sinon `store.one(X)` | `LookupError` si introuvable / ambiguë |
| absente | — | `TypeError` à la déclaration |
| autre (`dict`, `str`, `Store`, …) | — | `TypeError` à la déclaration |

Les valeurs injectées sont **deep-copiées** par défaut : un module ne peut pas corrompre l'état lu par
un autre. `Pipeline.run(copy_inputs=False)` désactive la copie quand le volume l'impose — la garantie
d'isolation disparaît alors, et c'est un choix conscient, pas un défaut.

## Règles de sortie (retour)

L'annotation de retour est **obligatoire** et constitue le contrat de sortie.

| Retour | Effet |
|---|---|
| `None` | Aucun changement. Module en lecture seule (export, contrôle, métriques). |
| une `Entity` / un `Config` | Upsert. |
| un itérable de `Entity` / `Config` / `Patch` / `Delete` | Appliqué dans l'ordre. |

```python
-> list[Order]                            # crée / remplace des Order
-> list[Patch[MarketArea]]                # met à jour quelques champs
-> list[Delete[Order]]                    # supprime
-> list[Order | Patch[MarketArea]]        # plusieurs types, plusieurs opérations
-> None                                   # ne touche à rien
```

Produire un type non déclaré est une `TypeError`. Le contrat distingue :

- **produit** (`-> list[Order]`) : le type peut ne pas exister avant, il sera créé ;
- **touché** (`Patch[X]`, `Delete[X]`) : le type doit exister avant.

C'est ce qui permet à `check` de raisonner sur le chaînage — voir [Validation](validation.md).

## `Step` — configuration par étape

Un pipeline peut lancer **deux fois le même module avec des paramètres différents** (clearing J-1 puis
intraday, deux zones, deux horizons). La config vit donc au niveau de l'étape :

```python
Pipeline(
    Step(clearing, ClearingParams(mode="DA"), name="clearing_da"),
    Step(clearing, ClearingParams(mode="ID"), name="clearing_id"),
    settlement,                       # module nu : config lue dans le Store
)
```

- `Step(module, *configs, name=None)` — `name` défaut = nom de la fonction, suffixé si doublon.
- Résolution d'une `Config` : d'abord les configs de l'étape, sinon `store.one(...)`.
- Un module nu passé à `Pipeline` est équivalent à `Step(module)`.

## `Pipeline`

| Méthode | Effet |
|---|---|
| `run(store, *, copy_inputs=True, on_step=None)` | `check`, puis exécute les étapes dans l'ordre. Retourne le `store` muté. |
| `check(store)` | Valide le chaînage sans rien exécuter. |
| `explain()` | Rend le graphe lectures / créations / modifications, une ligne par étape. |

`on_step(step, store)` est appelé après chaque étape : logs, métriques, snapshot, écriture des sorties.
Un seul hook, il couvre tous les besoins d'observabilité.
