# Contributing to morph

## Setup

```bash
uv sync
```

## Before opening a PR

```bash
uv run pytest --cov=morph      # tests + coverage
uv run ruff check morph tests  # lint
uv run ruff format morph tests # format
uv run ty check                 # typecheck
```

All three checks (lint, typecheck, test) run in CI on every pull request — they must pass locally before
pushing.

## Commit convention

One commit = one logical change, imperative-mood message describing *why* rather than *what* (the diff
already shows the what).

## PR process

1. One branch per change, off `main`.
2. CI (lint/typecheck/test) must be green.
3. One review before merge.

## Documentation

The docs site (`docs/`) is built with [zensical](https://zensical.org):

```bash
uv run --group docs zensical serve   # local preview on localhost:8000
```

`SPEC.md`, at the repo root, is the full project specification — more detailed than the docs site, and it
also includes the internal adoption plan.
