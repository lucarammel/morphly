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

    ``list[X]`` (X: Entity) -> every instance of X
    ``X`` (X: Config)       -> the step config, else the store singleton
    return                  -> Entity/Config to upsert, Patch/Delete to apply
    """

    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn
        self.name = fn.__name__
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
        """Run the function, returning its operations without applying them."""
        kwargs: dict[str, Any] = {}
        for param, is_collection, cls in self.reads:
            value: Any = store.all(cls) if is_collection else _config(cls, configs, store)
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
    """Turn an annotated function into a module."""
    return Module(fn)


def _config[C: Config](cls: type[C], configs: tuple[Config, ...], store: Store) -> C:
    hits = [c for c in configs if isinstance(c, cls)]
    if len(hits) > 1:
        raise LookupError(f"several {cls.__name__} bound to the same step")
    return hits[0] if hits else store.one(cls)


class Step:
    """A module plus the configs bound to that occurrence of it."""

    def __init__(self, module_: Module | Callable[..., Any], *configs: Config, name: str | None = None):
        self.module = module_ if isinstance(module_, Module) else Module(module_)
        self.configs = configs
        self.name = name or self.module.name

    def __repr__(self) -> str:
        return f"{self.name}: {self.module!r}"


class Pipeline:
    """An ordered list of steps, checked before it runs."""

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
        """Validate the chaining on types only, without running anything."""
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
        on_step: Callable[[Step, Store], None] | None = None,
    ) -> Store:
        """Check, then run every step in order and apply its output. Mutates and returns ``store``."""
        self.check(store)
        for step in self.steps:
            ops = step.module(store, step.configs, copy_inputs)
            _apply(ops, store, step.module.touches)
            if on_step:
                on_step(step, store)
        return store

    def explain(self) -> str:
        """One line per step: reads(), then produced and ~touched types."""
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
            obj: Entity = store.find(declared, op.target.name)
            if isinstance(op, Patch):
                check_fields(obj, op.fields)
            resolved.append((op, obj))
        else:
            resolved.append((op, None))
    for op, stored in resolved:
        if isinstance(op, Delete) and stored is not None:
            store.drop(stored)
        elif isinstance(op, Patch) and stored is not None:
            store.patch(stored, op.fields)
        else:
            store.put(op)  # type: ignore[arg-type]
