# Changelog

All notable changes to this project will be documented in this file.

---

## Versioning

- `MAJOR` version when you make incompatible API changes,
- `MINOR` version when you add functionality in a backwards compatible manner,
- `PATCH` version when you make backwards compatible bug fixes.

---

## Release History Legend

- ✨ Feature
- 🐛 Fix
- 🔄 Change
- 🧹 Refactor
- 📚 Docs
- 🔒 Security

---

## Unreleased

- ✨ `Put[E]` is an explicit creation marker, so a return annotation can spell out all three verbs —
  `-> list[Put[Payslip] | Patch[Employee] | Delete[Timesheet]]` — instead of leaving creation implicit in
  a bare type. Pure sugar: returning a bare `Entity`/`Config` still creates it (#65).

## 0.1.1 — 2026-08-08

- ✨ `Store.history(obj)` returns every write a run made to an object — which step, which action, which
  fields — recorded from the single place all writes go through (#56).
- ✨ `Workflow.run(store, atomic=True)` rolls the store back to its initial state if any step raises,
  making the whole run all-or-nothing instead of just each step (#35).
- ✨ `check()` reports a type produced further down the list as an ordering problem, naming the step to
  move and its position, instead of reporting the type as simply absent (#54).
- ✨ An exception raised by a module, or while applying its output, is re-raised unchanged with a note
  naming the step, its position and the state of the store (#55).
- 🔄 **Breaking**: `Workflow.run` only fills `last_run` when passed `record=True`. Recording costs one
  deep copy of the store per step and was previously paid by every run, including the ones that never
  replay (#53).
- 🐛 Pre-commit's `ruff-format`/`ruff-check` hooks matched `files: ^morph/`, a leftover from before the
  package was renamed to `morphly`; they ran on nothing.

## 0.1.0 — 2026-08-07

First release.

- ✨ Initial API: `Entity`, `Config`, `Store`, `@module`/`Module`, `Step`, `Workflow`, `Patch`, `Delete`,
  `view`.
- ✨ `Workflow.to_mermaid()` renders the dataflow as a Mermaid flowchart (#32).
- ✨ `on_step` receives the operations a step just wrote, not just its name (#30).
- ✨ `Store.drop()` and `Store.patch()` can target by `(type, name)`, not only by instance (#31).
- ✨ `Workflow.run(reuse=...)` skips steps whose inputs are unchanged since a previous run (#33).
- 🐛 `check()` now validates the `Config` a module reads, not only the entities (#28).
- 🐛 A step that `Patch`es a target it already `Delete`d in the same step now raises a clear error
  instead of an opaque `KeyError` (#29).
- 🔄 **Breaking**: renamed the package `morph` → `morphly` and `Pipeline` → `Workflow`, ahead of the
  first PyPI publish.
- 🔄 Lowered `requires-python` to 3.12 (#34).
- 🧹 Split the single module into `entity.py` / `module.py` / `operations.py` / `store.py` /
  `workflow.py`, one per concept.
- 📚 Added the documentation site (zensical, deployed to GitHub Pages), CONTRIBUTING/SECURITY/code of
  conduct, and a `py.typed` marker (#4, #5, #7).
