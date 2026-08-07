"""Modules, steps and pipelines. The function signature is the contract."""

from __future__ import annotations

import copy
import inspect
import typing
from collections.abc import Callable, Iterable, Iterator
from typing import Any, get_args, get_origin

from morph.store import Config, Delete, Entity, Patch, Store, check_fields

_Op = Entity | Config | Patch[Any] | Delete[Any]


def _nodes(annotation: Any) -> Iterator[Any]:
    """Walk a return annotation, stopping at Patch[...] / Delete[...] leaves."""
    if get_origin(annotation) in (Patch, Delete) or not get_args(annotation):
        yield annotation
        return
    for arg in get_args(annotation):
        yield from _nodes(arg)


class Module:
    """A function whose annotations declare what it reads, creates and touches.

    Built by the [`@module`][morph.module] decorator; you rarely instantiate it
    yourself. The annotations are parsed once, at import time, and an unsupported or
    missing one fails there rather than mid-run.

    | Annotation | Injected |
    | --- | --- |
    | `list[X]`, `X: Entity` | `store.all(X)`, subclasses included |
    | `X`, `X: Config` | the step's config, else `store.one(X)` |

    The return annotation forms the output contract: `Entity` and `Config` types are
    *produced*, types inside `Patch[...]` and `Delete[...]` are *touched*, and `None`
    means the module writes nothing.

    Args:
        fn: The annotated function to wrap.

    Attributes:
        fn: The wrapped function.
        name: The function's name, used as the default step name.
        reads: One `(parameter, is_collection, type)` triple per parameter.
        produces: Entity and config types the module creates or replaces.
        touches: Entity types the module patches or deletes.

    Raises:
        TypeError: If a parameter is unannotated, if an annotation is not
            `list[Entity subclass]` or a `Config` subclass, if the return is
            unannotated, or if `Patch`/`Delete` is used without a type parameter.
    """

    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn
        self.name = getattr(fn, "__name__", type(fn).__name__)
        hints = typing.get_type_hints(fn)
        self.reads: list[tuple[str, bool, type]] = []
        for param in inspect.signature(fn).parameters:
            self.reads.append((param, *self._read(param, hints.get(param))))
        if "return" not in hints:
            raise TypeError(f"{self.name}: the return type must be annotated (use `-> None` if it writes nothing)")
        self.produces, self.touches = self._outputs(hints["return"])

    def _read(self, param: str, annotation: Any) -> tuple[bool, type]:
        if annotation is None:
            raise TypeError(f"{self.name}: parameter {param!r} must be annotated")
        if get_origin(annotation) is list:
            (inner,) = get_args(annotation)
            if not (isinstance(inner, type) and issubclass(inner, Entity)):
                raise TypeError(f"{self.name}: list[{inner}] — the element type must be an Entity")
            return True, inner
        if isinstance(annotation, type) and issubclass(annotation, Config):
            return False, annotation
        raise TypeError(
            f"{self.name}: unsupported annotation for {param!r}: {annotation}. "
            f"Expected list[Entity subclass] or a Config subclass."
        )

    def _outputs(self, annotation: Any) -> tuple[list[type], list[type]]:
        produces: list[type] = []
        touches: list[type] = []
        for node in _nodes(annotation):
            if node in (Patch, Delete):
                raise TypeError(f"{self.name}: annotate {node.__name__}[YourEntity], not a bare {node.__name__}")
            origin = get_origin(node)
            if origin in (Patch, Delete):
                touches.extend(a for a in get_args(node) if isinstance(a, type) and issubclass(a, Entity))
            elif isinstance(node, type) and issubclass(node, (Entity, Config)):
                produces.append(node)
        return produces, touches

    def __call__(self, store: Store, configs: tuple[Config, ...] = (), copy_inputs: bool = True) -> list[_Op]:
        """Run the function, returning its operations without applying them.

        Useful on its own to unit-test a module: build a `Store`, call the module, and
        assert on the operations it returns — nothing is written.

        Args:
            store: The state to read from.
            configs: Configs bound to this step, tried before `store.one`.
            copy_inputs: Deep-copy every injected value, so the module cannot corrupt
                the state read by another one. Turn off only when volume demands it.

        Returns:
            The operations the module returned, validated against its contract but not
            yet applied. Empty if the module returned `None`.

        Raises:
            TypeError: If the module returned an operation its signature does not
                declare.
            LookupError: If a required config is neither bound to the step nor in the
                store.
        """
        kwargs: dict[str, Any] = {}
        for param, is_collection, cls in self.reads:
            value: Any = (
                store.all(cls)  # ty: ignore[invalid-argument-type]
                if is_collection
                else _config(cls, configs, store)  # ty: ignore[invalid-argument-type]
            )
            kwargs[param] = copy.deepcopy(value) if copy_inputs else value
        result = self.fn(**kwargs)
        if result is None:
            return []
        ops: list[_Op] = [result] if isinstance(result, (Entity, Config, Patch, Delete)) else list(result)
        for op in ops:
            self._check_declared(op)
        return ops

    def _check_declared(self, op: _Op) -> None:
        if isinstance(op, (Patch, Delete)):
            if not any(isinstance(op.target, t) for t in self.touches):
                raise TypeError(
                    f"{self.name} returned {op!r} but {type(op).__name__}"
                    f"[{type(op.target).__name__}] is not in its return type"
                )
        elif not any(isinstance(op, t) for t in self.produces):
            raise TypeError(f"{self.name} produced a {type(op).__name__}, which is not in its return type")

    def __repr__(self) -> str:
        reads = ", ".join(f"{c.__name__}{'[]' if many else ''}" for _, many, c in self.reads) or "-"
        writes = ", ".join([t.__name__ for t in self.produces] + [f"~{t.__name__}" for t in self.touches]) or "-"
        return f"{self.name}({reads}) -> {writes}"


def module(fn: Callable[..., Any]) -> Module:
    """Turn an annotated function into a module.

    There is no base class to inherit from and nothing to register: the decorator reads
    the annotations and that is the whole contract. Errors in the contract are raised
    at import time.

    Args:
        fn: A function whose parameters are annotated `list[Entity subclass]` or
            `Config subclass`, and whose return type is annotated.

    Returns:
        A [`Module`][morph.Module], ready to be dropped into a
        [`Pipeline`][morph.Pipeline].

    Raises:
        TypeError: If the signature does not form a valid contract.

    Examples:
        ```python
        @module
        def compute_gross(
            employees: list[Employee],
            sheets: list[Timesheet],
            policy: PayrollPolicy,
        ) -> list[Patch[Employee]]:
            hours = {s.employee: s.hours for s in sheets}
            return [Patch(e, gross=e.hourly_rate * hours.get(e.name, 0.0)) for e in employees]
        ```
    """
    return Module(fn)


def _config[C: Config](cls: type[C], configs: tuple[Config, ...], store: Store) -> C:
    hits = [c for c in configs if isinstance(c, cls)]
    if len(hits) > 1:
        raise LookupError(f"several {cls.__name__} bound to the same step")
    return hits[0] if hits else store.one(cls)


class Step:
    """A module plus the configs bound to that occurrence of it.

    Configs live on the step, not on the module, so the same module can appear twice in
    a pipeline with different parameters. A config bound here wins over the one in the
    [`Store`][morph.Store].

    Args:
        module_: A [`Module`][morph.Module], or a plain function wrapped on the fly.
        *configs: Configs bound to this occurrence.
        name: Step name for `explain` and `on_step`. Defaults to the function's name,
            suffixed on collision within a pipeline.

    Attributes:
        module: The wrapped module.
        configs: The configs bound to this step.
        name: The step name.

    Examples:
        ```python
        Pipeline(
            Step(withhold, PayrollPolicy(social_rate=0.22), name="withhold_fr"),
            Step(withhold, PayrollPolicy(social_rate=0.13), name="withhold_uk"),
        )
        ```
    """

    def __init__(self, module_: Module | Callable[..., Any], *configs: Config, name: str | None = None):
        self.module = module_ if isinstance(module_, Module) else Module(module_)
        self.configs = configs
        self.name = name or self.module.name

    def __repr__(self) -> str:
        return f"{self.name}: {self.module!r}"


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
            available |= set(step.module.produces)

    def run(
        self,
        store: Store,
        *,
        copy_inputs: bool = True,
        on_step: Callable[[Step, list[_Op], Store], None] | None = None,
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

        Returns:
            The same `store`, mutated.

        Raises:
            LookupError: If [`check`][morph.Pipeline.check] fails, or a config is
                missing.
            TypeError: If a module returns an operation it did not declare.
            KeyError: If a `Patch` or `Delete` target is missing or ambiguous.
            ValueError: If a `Patch` names a field the target does not have.
            pydantic.ValidationError: If a written value does not validate.
        """
        self.check(store)
        for step in self.steps:
            ops = step.module(store, step.configs, copy_inputs)
            _apply(ops, store, step.module.touches)
            if on_step:
                on_step(step, ops, store)
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

    def __repr__(self) -> str:
        return f"Pipeline({', '.join(s.name for s in self.steps)})"


def _entity(cls: type) -> bool:
    return issubclass(cls, Entity)


def _apply(ops: Iterable[_Op], store: Store, touches: list[type]) -> None:
    """Apply a step's operations, after resolving and checking every target.

    ``Patch``/``Delete`` targets are resolved against the type declared in the return
    annotation, so a module can hand back an enriched view of a stored object.
    """
    resolved: list[tuple[_Op, Entity | None]] = []
    for op in ops:
        if isinstance(op, (Patch, Delete)):
            declared = next(t for t in touches if isinstance(op.target, t))
            obj: Entity = store.find(declared, op.target.name)  # ty: ignore[invalid-argument-type]
            if isinstance(op, Patch):
                check_fields(obj, op.fields)
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
