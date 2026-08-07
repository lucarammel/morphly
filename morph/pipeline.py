"""Pipelines: an ordered list of steps, checked before it runs."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from typing import Any

from morph.entity import Config, Entity
from morph.module import Module, Step, _config, _Op
from morph.operations import Delete, Patch, check_fields
from morph.store import Store


class _RunCache:
    """The reusable half of a `run`: one input key, snapshot and ops per step name."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, tuple[tuple[tuple[str, ...], ...], Store, list[_Op]]] = {}

    def hit(self, step_name: str, key: tuple[tuple[str, ...], ...]) -> tuple[Store, list[_Op]] | None:
        entry = self._entries.get(step_name)
        if entry is None or entry[0] != key:
            return None
        return copy.deepcopy(entry[1]), entry[2]

    def record(self, step_name: str, key: tuple[tuple[str, ...], ...], store: Store, ops: list[_Op]) -> None:
        self._entries[step_name] = (key, copy.deepcopy(store), ops)


def _input_key(step: Step, store: Store) -> tuple[tuple[str, ...], ...]:
    """A hashable snapshot of everything a step would read right now.

    One tuple per parameter, so two runs that inject the same objects in a different
    shape never compare equal by accident.
    """
    key: list[tuple[str, ...]] = []
    for _, is_collection, cls in step.module.reads:
        if is_collection:
            objs = sorted(store.all(cls), key=lambda o: (type(o).__name__, o.name))  # ty: ignore[invalid-argument-type]
            key.append(tuple(o.model_dump_json() for o in objs))
        else:
            key.append((_config(cls, step.configs, store).model_dump_json(),))  # ty: ignore[invalid-argument-type]
    return tuple(key)


class Pipeline:
    """An ordered list of steps, checked before it runs.

    The order is yours: a pipeline is a list, not a scheduler. What it does guarantee is
    that an inconsistent order — a step reading a type nobody upstream provides — fails
    in a millisecond instead of three hours in.

    Args:
        *steps: [`Step`][morph.Step] instances, modules, or plain functions. A bare
            module is equivalent to `Step(module)`.

    Attributes:
        steps: The steps, in order, with duplicate names suffixed (`pay`, `pay_2`).
        last_run: Cache of the most recent `run`, in memory. Pass it as `reuse` to a
            later `run` to skip steps whose inputs haven't changed. `None` before the
            first run.

    Examples:
        ```python
        pipeline = Pipeline(
            Step(compute_gross, PayrollPolicy(overtime_after=35.0)),
            withhold,
            archive_timesheets,
        )
        pipeline.run(store)
        ```
    """

    def __init__(self, *steps: Step | Module | Callable[..., Any]):
        self.steps = [s if isinstance(s, Step) else Step(s) for s in steps]
        self._dedupe_names()
        self.last_run: _RunCache | None = None

    def _dedupe_names(self) -> None:
        seen: dict[str, int] = {}
        for step in self.steps:
            count = seen.get(step.name, 0)
            seen[step.name] = count + 1
            if count:
                step.name = f"{step.name}_{count + 1}"

    def check(self, store: Store) -> None:
        """Validate the chaining on types only, without running anything.

        Replays the pipeline on types: it starts from `store.types()` and adds, after
        each step, the types that step produces. A step reading or touching a type that
        is neither in the initial store nor produced upstream is an error.

        Called automatically by [`run`][morph.Pipeline.run]; call it yourself to fail at
        startup, before loading any data.

        Args:
            store: The state the pipeline would run on. Only its types are read.

        Raises:
            LookupError: If a step reads or touches a type nobody provides.
        """
        available = store.types()
        for step in self.steps:
            needed = [(f"reads {c.__name__}", c) for _, _, c in step.module.reads if _entity(c)]
            needed += [(f"touches {c.__name__}", c) for c in step.module.touches]
            for label, cls in needed:
                if not any(issubclass(t, cls) for t in available):
                    raise LookupError(
                        f"step {step.name!r} {label}, which is neither in the store nor produced by an upstream step"
                    )
            for _, is_collection, cls in step.module.reads:
                if is_collection or _entity(cls):
                    continue
                bound = any(isinstance(c, cls) for c in step.configs)
                if not bound and not any(issubclass(t, cls) for t in available):
                    raise LookupError(
                        f"step {step.name!r} reads {cls.__name__}, which is neither bound to the step "
                        "nor in the store nor produced by an upstream step"
                    )
            available |= set(step.module.produces)

    def run(
        self,
        store: Store,
        *,
        copy_inputs: bool = True,
        on_step: Callable[[Step, list[_Op], Store], None] | None = None,
        reuse: _RunCache | None = None,
    ) -> Store:
        """Check, then run every step in order and apply its output.

        A step's operations are collected and validated before any of them is written,
        so a step never applies halfway. The pipeline as a whole is not transactional:
        for a non-destructive run, pass `copy.deepcopy(store)`.

        Args:
            store: The state to run on. **Mutated in place.**
            copy_inputs: Deep-copy the values injected into each module. Turning this
                off drops the isolation guarantee — a module mutating an input then
                affects the shared state.
            on_step: Called as `on_step(step, ops, store)` after each step is applied,
                with the operations it just wrote. The hook for logs, metrics,
                provenance and writing intermediate outputs.
            reuse: A previous [`last_run`][morph.Pipeline.last_run] to replay from. A
                step whose reads are byte-for-byte identical to that run is skipped —
                its recorded outcome is restored from an in-memory snapshot instead of
                calling the module again. The first step whose reads differ, and every
                step after it, runs for real. Handy in a notebook: touch step 12, rerun,
                the first 11 are skipped.

        Returns:
            The same `store`, mutated.

        Raises:
            LookupError: If [`check`][morph.Pipeline.check] fails, or a config is
                missing.
            TypeError: If a module returns an operation it did not declare.
            KeyError: If a `Patch` or `Delete` target is missing or ambiguous.
            ValueError: If a `Patch` names a field the target does not have, or if a
                step returns an operation on a target it already deleted.
            pydantic.ValidationError: If a written value does not validate.
        """
        self.check(store)
        cache = _RunCache()
        for step in self.steps:
            key = _input_key(step, store)
            hit = reuse.hit(step.name, key) if reuse else None
            if hit is None:
                ops = step.module(store, step.configs, copy_inputs)
                _apply(ops, store, step.module.touches, step.name)
            else:
                snapshot, ops = hit
                store.__dict__.update(snapshot.__dict__)
            cache.record(step.name, key, store, ops)
            if on_step:
                on_step(step, ops, store)
        self.last_run = cache
        return store

    def explain(self) -> str:
        """One line per step: reads(), then produced and ~touched types.

        Returns:
            A rendering of the pipeline's dataflow, for logs and reviews. Touched types
            are prefixed with `~`.

        Examples:
            ```text
            1. compute_gross: compute_gross(Employee[], Timesheet[], PayrollPolicy) -> ~Employee
            2. withhold: withhold(Employee[], PayrollPolicy) -> Payslip
            3. archive: archive(Timesheet[]) -> ~Timesheet
            ```
        """
        return "\n".join(f"{i}. {s!r}" for i, s in enumerate(self.steps, 1))

    def to_mermaid(self) -> str:
        """Render the pipeline's dataflow as a Mermaid flowchart.

        Same information as [`explain`][morph.Pipeline.explain], as a graph instead of a
        line per step: every edge is a `reads`/`produces`/`touches` relationship already
        present in the modules' signatures, so the graph cannot go stale.

        Returns:
            A `flowchart LR` block: `Type --> step` for entity reads, `step --> Type`
            for produced types, `step -.-> Type` for touched types.

        Examples:
            ```python
            print(pipeline.to_mermaid())
            ```
            ```text
            flowchart LR
                Employee --> compute_gross
                Timesheet --> compute_gross
                compute_gross -.-> Employee
                Employee --> withhold
                withhold --> Payslip
            ```
        """
        edges: dict[str, None] = {}
        for step in self.steps:
            for _, _, cls in step.module.reads:
                if _entity(cls):
                    edges[f"{cls.__name__} --> {step.name}"] = None
            for cls in step.module.produces:
                edges[f"{step.name} --> {cls.__name__}"] = None
            for cls in step.module.touches:
                edges[f"{step.name} -.-> {cls.__name__}"] = None
        return "flowchart LR\n" + "\n".join(f"    {edge}" for edge in edges)

    def __repr__(self) -> str:
        return f"Pipeline({', '.join(s.name for s in self.steps)})"


def _entity(cls: type) -> bool:
    return issubclass(cls, Entity)


def _apply(ops: Iterable[_Op], store: Store, touches: list[type], step_name: str) -> None:
    """Apply a step's operations, after resolving and checking every target.

    ``Patch``/``Delete`` targets are resolved against the type declared in the return
    annotation, so a module can hand back an enriched view of a stored object.
    """
    resolved: list[tuple[_Op, Entity | None]] = []
    deleted: set[tuple[type, str]] = set()
    for op in ops:
        if isinstance(op, (Patch, Delete)):
            declared = next(t for t in touches if isinstance(op.target, t))
            key = (declared, op.target.name)
            if key in deleted:
                raise ValueError(
                    f"{step_name} returned a {type(op).__name__} on {declared.__name__} {op.target.name!r} "
                    "which the same step deletes"
                )
            obj: Entity = store.find(declared, op.target.name)  # ty: ignore[invalid-argument-type]
            if isinstance(op, Patch):
                check_fields(obj, op.fields)
            else:
                deleted.add(key)
            resolved.append((op, obj))
        else:
            resolved.append((op, None))
    for op, stored in resolved:
        if isinstance(op, Delete):
            assert stored is not None
            store.drop(stored)
        elif isinstance(op, Patch):
            assert stored is not None
            store.patch(stored, op.fields)
        elif isinstance(op, (Entity, Config)):
            store.put(op)
