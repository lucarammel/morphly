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
