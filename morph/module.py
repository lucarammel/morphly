"""Modules and steps: the function signature is the contract."""

from __future__ import annotations

import copy
import inspect
import typing
from collections.abc import Callable, Iterator
from typing import Any, get_args, get_origin

from morph.entity import Config, Entity
from morph.operations import Delete, Patch
from morph.store import Store

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
