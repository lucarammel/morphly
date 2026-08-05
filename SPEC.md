# morph — spécification

`morph` orchestre des **modules indépendants** qui partagent un **jeu d'objets métier communs**.
Chaque module lit le sous-ensemble d'objets dont il a besoin, et déclare ce qu'il modifie.

Version : 0.1.0 · Python ≥ 3.13 · une seule dépendance : `pydantic`.

---

## 1. Problème

Chaîner N modules de calcul sur un état métier partagé, avec :

- des objets métier communs, typés et validés ;
- des modules qui ne connaissent ni l'orchestrateur ni les autres modules ;
- un contrat explicite : ce qu'un module lit, ce qu'il crée, ce qu'il touche ;
- un échec **avant** le calcul quand le chaînage est incohérent.

Les orchestrateurs maison convergent tous vers les mêmes défauts, que `morph` refuse par construction :

| Défaut classique | Ce que fait `morph` |
|---|---|
| Registre global `enum -> classe` à modifier pour chaque nouvel objet | Le **type est la clé**. Rien à enregistrer. |
| Modifications transportées en `dict[str, Any]` non validés | Un module renvoie des **objets pydantic** ou des `Patch` typés. |
| 5–6 méthodes abstraites de plomberie par module | Un module est **une fonction annotée**. |
| Besoins déclarés à la main (`get_objects_used()`) et jamais vérifiés | Les besoins **sont** la signature, et ils sont vérifiés. |
| Résolution de références par nom, à la main, dans le handler | Les objets lus sont les objets du `Store`. |
| Mutations qui fuient d'un module à l'autre | Seul le **retour** est appliqué. |
| `deepcopy` de tout l'état à chaque étape | Copie du **seul sous-ensemble lu**, désactivable. |

## 2. Principes

1. **Le type est la clé.** Pas d'enum, pas de mapping nom→classe, pas de registre.
2. **La signature est le contrat.** Les annotations décrivent entrées et sorties ; le noyau les lit.
3. **Pas d'effet de bord implicite.** Muter une entrée n'a aucun effet ; seul le retour est appliqué.
4. **Échouer avant de calculer.** Une incohérence de chaînage est une erreur au démarrage.
5. **Zéro cérémonie.** Aucune classe à hériter pour écrire un module.

## 3. Modèle de données

### 3.1 `Entity`

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

### 3.2 `Config`

Entrée **singleton** : paramètres d'un module, réglages globaux, contexte.

```python
class BidParams(Config):
    margin: float = 1.0
    temporal: Temporal = Temporal()   # imbrication libre, c'est du pydantic
```

- Pas de `name`. Résolu par type, soit sur l'étape, soit dans le `Store` (§4.3).

### 3.3 `Store`

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
| `types()` | Types présents (utilisé par `Pipeline.check`). |

**Résolution des cibles.** Un module travaille souvent sur une *vue* enrichie (`MarketAreaMC(MarketArea)`),
et renvoie `Patch(mc_area, price=...)`. La cible est résolue sur le type **déclaré dans l'annotation de
retour** (`Patch[MarketArea]`), pas sur la classe de la vue : la vue peut donc être une sœur du type stocké.
`Store.find` cherche d'abord le bucket du type exact, puis la lignée ; l'ambiguïté (deux objets de même
`name` dans deux types frères) est une erreur explicite, pas un choix arbitraire.

Le `Store` est un objet Python ordinaire : `copy.deepcopy(store)` est un snapshot, `pickle` le persiste.

### 3.4 Sorties : `Patch[E]` et `Delete[E]`

```python
Patch(order, accepted_power=ts, spread=0.3)   # mise à jour partielle
Delete(order)                                 # suppression
```

- `Patch` n'écrit que les champs fournis — c'est la sortie normale d'un module qui calcule quelques
  attributs sur des objets existants sans toucher au reste (ni aux références vers lui).
- Renvoyer une `Entity` complète = création ou **remplacement intégral**.
- Le paramètre de type est **obligatoire dans l'annotation de retour** : `list[Patch[Order]]`.
  C'est ainsi que le module déclare qu'il touche `Order`. `list[Patch]` nu est une erreur de déclaration.

### 3.5 `view` (sucre)

```python
mc_order = view(OrderMC, order, times=times, timestep=timestep)
```

Construit une vue enrichie à partir d'une entité partagée : copie superficielle des champs de la source,
plus les extras, puis validation pydantic de la classe cible. Remplace le `model_validate({**shallow_dump(obj), ...})`
écrit à la main dans chaque module.

## 4. API des modules

Un module est une fonction décorée par `@module`.

```python
@module
def bidding(plants: list[Plant], params: BidParams) -> list[Order]:
    return [Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost * params.margin) for p in plants]
```

### 4.1 Règles d'injection (paramètres)

| Annotation | Reçoit | Erreur |
|---|---|---|
| `list[X]`, `X: Entity` | `store.all(X)` — liste, éventuellement vide | `TypeError` si `X` n'est pas une `Entity` |
| `X`, `X: Config` | la config de l'étape, sinon `store.one(X)` | `LookupError` si introuvable / ambiguë |
| absente | — | `TypeError` à la déclaration |
| autre (`dict`, `str`, `Store`, …) | — | `TypeError` à la déclaration |

Les valeurs injectées sont **deep-copiées** par défaut : un module ne peut pas corrompre l'état lu par
un autre. `Pipeline.run(copy_inputs=False)` désactive la copie quand le volume l'impose — la garantie
d'isolation disparaît alors, et c'est un choix conscient, pas un défaut.

### 4.2 Règles de sortie (retour)

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

C'est ce qui permet à `check` de raisonner sur le chaînage.

### 4.3 `Step` — configuration par étape

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

### 4.4 `Pipeline`

| Méthode | Effet |
|---|---|
| `run(store, *, copy_inputs=True, on_step=None)` | `check`, puis exécute les étapes dans l'ordre. Retourne le `store` muté. |
| `check(store)` | Valide le chaînage sans rien exécuter. |
| `explain()` | Rend le graphe lectures / créations / modifications, une ligne par étape. |

`on_step(step, store)` est appelé après chaque étape : logs, métriques, snapshot, écriture des sorties
dans `output_dir / step.name`. Un seul hook, il couvre tous les besoins d'observabilité.

## 5. Validation

Trois barrières, de la plus précoce à la plus tardive.

| Quand | Ce qui est vérifié | Exception |
|---|---|---|
| `@module` (import) | Chaque paramètre annoté, annotation supportée, retour annoté, `Patch`/`Delete` paramétrés | `TypeError` |
| `check` (démarrage de `run`) | Chaque type lu ou touché est fourni par le `Store` initial ou par une étape amont | `LookupError` |
| par étape, avant application | Contrat de sortie respecté ; cibles de `Patch`/`Delete` présentes et non ambiguës ; champs de `Patch` existants | `TypeError` / `KeyError` / `ValueError` |
| à l'application | Validation pydantic de chaque objet et de chaque champ écrit | `ValidationError` |

`check` simule le pipeline sur les **types** : il part de `store.types()` et ajoute après chaque étape
les types qu'elle produit. Un module qui lit `Trade` alors qu'aucune étape amont n'en produit et que le
`Store` n'en contient pas échoue en une milliseconde, pas après trois heures de calcul.

## 6. Sémantique d'application

- Les sorties d'une étape sont **collectées, validées, puis appliquées**. Une étape ne s'applique pas à moitié.
- Ordre d'application = ordre du retour. `put` puis `Delete` sur le même objet laisse l'objet supprimé.
- `put` sur un `(type, name)` existant **remplace** l'objet. Les mises à jour partielles passent par `Patch`.
- Le `Store` est muté en place. Pour un run non destructif : `pipeline.run(copy.deepcopy(store))`.

## 7. Non-objectifs

Volontairement absents, avec le point de bascule qui justifierait de les ajouter :

| Absent | Point de bascule |
|---|---|
| DAG, ordonnancement automatique | `Pipeline` est une liste ordonnée. À ajouter quand l'ordre manuel devient *faux*, pas quand il devient long. |
| Parallélisme | Quand deux étapes indépendantes dominent le temps mesuré. |
| Snapshots / rollback / diff intégrés | `deepcopy` couvre les cas. À intégrer si la mémoire devient le facteur limitant. |
| Chargement / écriture disque, formats | Hors périmètre : `morph` orchestre, l'appelant charge et écrit. |
| Filtres de portée déclaratifs (`get_filters`) | Filtrer relève du chargement (construire un `Store` réduit) ou du module. `Annotated[list[X], Where(...)]` est le point d'extension si ça se paie. |
| Chargement YAML/TOML des `Config` | `Params.model_validate(yaml.safe_load(p.read_text()))` tient sur une ligne, sans dépendance dans le noyau. |
| Pipeline déclaratif (fichier de workflow) | L'appelant mappe ses noms d'étapes vers ses fonctions ; c'est 5 lignes chez lui, et lui seul connaît ses noms. |
| Registre de plugins / entry-points | Quand les modules vivent dans des paquets tiers. |
| Branchements, boucles | Une fonction Python qui appelle deux `Pipeline` fait le travail. |

## 8. Exemple complet

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
    by_plant = {f"o_{p.name}": p for p in plants}
    return [
        op
        for o in orders
        for op in ([Patch(by_plant[o.name], cleared=o.volume)] if o.price < 30 else [Delete(o)])
    ]

store = Store(
    Plant(name="a", pmax=100, cost=10),
    Plant(name="b", pmax=50, cost=40),
    BidParams(margin=1.2),
)
Pipeline(Step(bidding, BidParams(margin=1.1)), clearing).run(store, on_step=lambda s, _: print(s.name))
```

## 9. Adoption par ATLAS

`morph` est dimensionné pour qu'ATLAS puisse s'y appuyer **module par module**, sans big-bang.
Ce qu'ATLAS garde : `io_utils` (chargement/écriture), `math` (timeseries, matrices), `solver`, `objects`,
et les `phases/` de chaque module — c'est-à-dire tout le métier. Ce qui disparaît : `orchestrator/`.

### 9.1 Correspondance

| ATLAS | `morph` |
|---|---|
| `BusinessModel` | `Entity` (mêmes garanties : `name` frozen, `validate_assignment`, `arbitrary_types_allowed`) |
| enum `BusinessModelName` + `MODEL_MAPPING_NAME` + `INVERSE_MODEL_MAPPING_NAME` | supprimés — le type est la clé |
| `Container[X]` / `AtlasDataset` | `Store` |
| `CurrentInputState` (+ snapshots, transaction, diff) | `Store` + `copy.deepcopy` |
| `XxxParameters` | `Config` |
| `AddObject` | renvoyer l'objet |
| `UpdateObject(name, {champs})` | `Patch(obj, **champs)` |
| `DeleteObject` | `Delete(obj)` |
| `ChangeSetHandler` (+ `_resolve_reference`) | `Pipeline.run` (plus de résolution manuelle : on lit les objets du `Store`) |
| `AbstractModule.import_data` + `InputDataset` | injection par annotations + `view(...)` |
| `get_business_model_class_used` / `get_filters` | la signature ; le filtrage passe au chargement |
| `validate_data` / `validates_results` | validateurs pydantic sur `Entity` / `Config` |
| `export_results` | `on_step`, ou une étape finale dédiée |
| `before_execution` / `after_execution` | `on_step` |
| `OutputDataset.build_change_sets` | le retour de la fonction |
| `Workflow` + `WorkflowJob` + `Step` + `WorkflowParameters` | `Pipeline(Step(...), ...)` |
| `ActionPlan` | l'appelant lance plusieurs `Pipeline` |

### 9.2 Pont, le temps de la transition

Six lignes chez ATLAS, à supprimer une fois la migration terminée :

```python
def to_store(dataset: AtlasDataset, *configs: Config) -> Store:
    return Store(*[obj for objs in dataset.to_dict().values() for obj in objs], *configs)

def to_dataset(store: Store) -> AtlasDataset:
    return AtlasDataset.from_dict({
        name: store.all(cls) for name, cls in cfg.MODEL_MAPPING_NAME.items()
    })
```

Un module migré tourne dans un `Pipeline`, les modules non migrés continuent à tourner sur l'`AtlasDataset` :
les deux vues restent synchronisables à chaque frontière.

### 9.3 Trajectoire

1. `class BusinessModel(Entity)` — les 20 objets métier héritent de `morph.Entity` sans autre changement.
2. Ajouter le pont `to_store` / `to_dataset`.
3. Migrer un module (le plus petit d'abord) : `module.py` + `input_dataset.py` + `output_dataset.py`
   deviennent **une fonction annotée** qui appelle les `phases/` inchangées. L'`InputDataset` qui construit
   les vues enrichies devient une poignée d'appels à `view(...)`, ou reste tel quel et prend le `Store` en entrée.
4. Remplacer `Workflow` par `Pipeline`, `WorkflowParameters` par la liste de `Step`. Le YAML de workflow, s'il
   reste nécessaire, se résout côté ATLAS : `{"market_clearing": clearing_module}` puis `Step(mapping[name], params)`.
5. Supprimer `atlas/orchestrator/` et `atlas/abstract_class/{module,dataset,orchestrator*}.py`.

### 9.4 Points d'attention

- **Volume.** ATLAS porte des timeseries lourdes dans ses objets. `copy_inputs=True` par défaut est un
  `deepcopy` du sous-ensemble lu : mesurer, puis passer à `copy_inputs=False` sur les pipelines massifs.
- **`Patch` plutôt qu'`Entity` complète.** Les modules ATLAS écrivent quelques attributs sur des objets
  volumineux et référencés ailleurs : `Patch` est la traduction fidèle d'`UpdateObject`, et évite de
  remplacer un objet vers lequel d'autres pointent.
- **Vues de module.** `OrderMC(Order)` reste légitime : la règle de lignée fait que `Patch(mc_order, ...)`
  atteint bien l'`Order` stocké.
- **Filtres.** `filter_equipments` / `filter_zones` restent côté chargement ATLAS ; on construit un `Store`
  déjà réduit.
