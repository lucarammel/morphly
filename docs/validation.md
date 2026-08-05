# Validation

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

## Sémantique d'application

- Les sorties d'une étape sont **collectées, validées, puis appliquées**. Une étape ne s'applique pas à moitié.
- Ordre d'application = ordre du retour. `put` puis `Delete` sur le même objet laisse l'objet supprimé.
- `put` sur un `(type, name)` existant **remplace** l'objet. Les mises à jour partielles passent par `Patch`.
- Le `Store` est muté en place. Pour un run non destructif : `pipeline.run(copy.deepcopy(store))`.
