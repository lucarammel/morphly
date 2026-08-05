# Non-objectifs

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
