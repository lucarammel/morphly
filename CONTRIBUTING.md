# Contribuer à morph

## Setup

```bash
uv sync
```

## Avant de proposer une PR

```bash
uv run pytest --cov=morph      # tests + couverture
uv run ruff check morph tests  # lint
uv run ruff format morph tests # format
uv run ty check                 # typage
```

Les trois checks (lint, typecheck, test) tournent en CI sur chaque pull request — ils doivent passer en
local avant de pousser.

## Convention de commit

Un commit = un changement logique, message à l'impératif décrivant le *pourquoi* plutôt que le *quoi*
(le diff montre déjà le quoi).

## Process de PR

1. Une branche par changement, depuis `main`.
2. La CI (lint/typecheck/test) doit être verte.
3. Une review avant merge.

## Documentation

Le site de doc (`docs/`) est construit avec [zensical](https://zensical.org) :

```bash
uv run --group docs zensical serve   # aperçu local sur localhost:8000
```

`SPEC.md`, à la racine, est la spécification complète du projet — plus détaillée que le site de doc, elle
inclut aussi le plan d'adoption interne.
