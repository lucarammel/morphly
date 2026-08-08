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

- ✨ An exception raised by a module, or while applying its output, is re-raised unchanged with a note
  naming the step, its position and the state of the store (#55).

- 🔄 **Breaking**: `Workflow.run` only fills `last_run` when passed `record=True`. Recording costs one
  deep copy of the store per step and was previously paid by every run, including the ones that never
  replay (#53).
